"""
Web Requirements Scraper - Fetch job requirements from URL
Usage: python web_requirements_scraper.py <url>
"""
import sys
import json
import re
from pathlib import Path
import requests
from bs4 import BeautifulSoup


def fetch_page(url):
    """Fetch HTML content from URL"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        return response.text
    except Exception as e:
        print(f"Error fetching URL: {e}")
        return None


def extract_text_from_html(html):
    """Extract clean text from HTML"""
    soup = BeautifulSoup(html, 'html.parser')
    
    # Remove script and style elements
    for script in soup(["script", "style"]):
        script.decompose()
    
    # Get text
    text = soup.get_text()
    
    # Clean up whitespace
    lines = (line.strip() for line in text.splitlines())
    chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
    text = '\n'.join(chunk for chunk in chunks if chunk)
    
    return text


def extract_kualifikasi_section(html):
    """Extract Kualifikasi section specifically"""
    soup = BeautifulSoup(html, 'html.parser')
    
    # Find "Kualifikasi" heading
    kualifikasi_heading = None
    for heading in soup.find_all(['h1', 'h2', 'h3', 'h4']):
        if 'kualifikasi' in heading.get_text().lower():
            kualifikasi_heading = heading
            break
    
    if not kualifikasi_heading:
        return None
    
    # Get all content after Kualifikasi until next heading
    content = []
    for sibling in kualifikasi_heading.find_next_siblings():
        if sibling.name in ['h1', 'h2', 'h3', 'h4']:
            break
        content.append(sibling.get_text())
    
    return '\n'.join(content)


def parse_kualifikasi(text):
    """Parse kualifikasi text and extract structured data"""
    data = {
        'gender': None,
        'age_range': None,
        'education': [],
        'location': None,
        'min_experience_years': 0,
        'experience_keywords': [],
        'skills': []
    }
    
    lines = text.split('\n')
    
    for line in lines:
        line_lower = line.lower().strip()
        
        # Gender
        if 'pria' in line_lower or 'wanita' in line_lower:
            if 'pria / wanita' in line_lower or 'pria/wanita' in line_lower:
                data['gender'] = None  # Both accepted
            elif 'wanita' in line_lower:
                data['gender'] = 'Female'
            elif 'pria' in line_lower:
                data['gender'] = 'Male'
        
        # Age
        age_match = re.search(r'usia\s+(?:maksimal\s+)?(\d+)\s*(?:-\s*(\d+))?\s*tahun', line_lower)
        if age_match:
            if age_match.group(2):  # Range
                data['age_range'] = {
                    'min': int(age_match.group(1)),
                    'max': int(age_match.group(2))
                }
            else:  # Max only
                data['age_range'] = {
                    'min': 18,
                    'max': int(age_match.group(1))
                }
        
        # Education
        if 'pendidikan' in line_lower:
            if 'sma' in line_lower or 'smk' in line_lower:
                data['education'].append('High School')
            if 'diploma' in line_lower or 'd3' in line_lower:
                data['education'].append('Diploma')
            if 'sarjana' in line_lower or 's1' in line_lower or 'bachelor' in line_lower:
                data['education'].append('Bachelor')
            if 'sederajat' in line_lower and not data['education']:
                data['education'] = ['High School', 'Diploma']
        
        # Location
        if 'penempatan' in line_lower:
            # Extract city name after "penempatan:"
            location_match = re.search(r'penempatan\s*:?\s*([A-Za-z\s]+)', line, re.IGNORECASE)
            if location_match:
                data['location'] = location_match.group(1).strip()
        
        # Experience years
        exp_match = re.search(r'(?:pengalaman|experience).*?(\d+)\s*tahun', line_lower)
        if exp_match:
            data['min_experience_years'] = int(exp_match.group(1))
        
        # Experience keywords
        if 'desk collection' in line_lower or 'call collection' in line_lower or 'telecollection' in line_lower:
            if 'desk collection' in line_lower:
                data['experience_keywords'].append('Desk Collection')
            if 'call collection' in line_lower:
                data['experience_keywords'].append('Call Collection')
            if 'telecollection' in line_lower:
                data['experience_keywords'].append('Telecollection')
            if 'debt collection' in line_lower:
                data['experience_keywords'].append('Debt Collection')
        
        # Skills - Communication
        if 'komunikasi' in line_lower or 'communication' in line_lower:
            if 'komunikasi' not in [s.lower() for s in data['skills']]:
                data['skills'].append('Communication')
        
        # Skills - Negotiation
        if 'negosiasi' in line_lower or 'negotiation' in line_lower:
            if 'negotiation' not in [s.lower() for s in data['skills']]:
                data['skills'].append('Negotiation')
        
        # Skills - Computer
        if 'komputer' in line_lower or 'computer' in line_lower:
            if 'computer skills' not in [s.lower() for s in data['skills']]:
                data['skills'].append('Computer Skills')
        
        # Skills - Microsoft Office
        if 'microsoft office' in line_lower or 'ms office' in line_lower:
            if 'microsoft office' not in [s.lower() for s in data['skills']]:
                data['skills'].append('Microsoft Office')
    
    return data


def build_requirements_json(parsed_data, position_title, job_description):
    """Build requirements JSON from parsed data"""
    
    # Default experience keywords if not found
    if not parsed_data['experience_keywords']:
        parsed_data['experience_keywords'] = ['Collection', 'Penagihan']
    
    requirements = {
        'position': position_title,
        'job_description': job_description[:500] + '...' if len(job_description) > 500 else job_description,
        'min_experience_years': parsed_data['min_experience_years'] or 1
    }
    
    # Experience keywords
    requirements['required_experience_keywords'] = parsed_data['experience_keywords']
    
    # Add common preferred keywords for collection positions
    if any(kw in str(parsed_data['experience_keywords']).lower() for kw in ['collection', 'penagihan']):
        requirements['preferred_experience_keywords'] = [
            'BPR', 'Bank Perkreditan Rakyat', 'Lembaga Keuangan',
            'Financial Institution', 'Banking', 'Finance'
        ]
    
    # Skills
    required_skills = {}
    for skill in parsed_data['skills']:
        if skill == 'Communication':
            required_skills[skill] = 10
        elif skill == 'Negotiation':
            required_skills[skill] = 10
        elif skill == 'Computer Skills':
            required_skills[skill] = 5
        elif skill == 'Microsoft Office':
            required_skills[skill] = 5
        else:
            required_skills[skill] = 5
    
    if required_skills:
        requirements['required_skills'] = required_skills
    
    # Add common preferred skills for collection
    requirements['preferred_skills'] = {
        'Problem Solving': 7,
        'Target Oriented': 7,
        'Customer Service': 6,
        'Persuasion': 6
    }
    
    # Education
    if parsed_data['education']:
        requirements['education_level'] = parsed_data['education']
    else:
        requirements['education_level'] = ['High School', 'Diploma', 'Bachelor']
    
    # Demographics
    if parsed_data['gender']:
        requirements['required_gender'] = parsed_data['gender']
    
    if parsed_data['location']:
        requirements['required_location'] = parsed_data['location']
    
    if parsed_data['age_range']:
        requirements['required_age_range'] = parsed_data['age_range']
    
    return requirements


def main():
    if len(sys.argv) < 2:
        print("Usage: python web_requirements_scraper.py <url>")
        print("\nExample:")
        print("  python web_requirements_scraper.py https://bprks.sarana.ai/screening-test/394f074b-dbb8-4e03-b55e-6a17621dfb6d")
        return
    
    url = sys.argv[1]
    
    print("="*70)
    print("WEB REQUIREMENTS SCRAPER")
    print("="*70)
    print(f"\nFetching: {url}")
    
    # Fetch page
    html = fetch_page(url)
    if not html:
        return
    
    print("✓ Page fetched successfully")
    
    # Extract kualifikasi section
    kualifikasi_text = extract_kualifikasi_section(html)
    if not kualifikasi_text:
        print("⚠ Could not find 'Kualifikasi' section, using full page")
        kualifikasi_text = extract_text_from_html(html)
    else:
        print("✓ Kualifikasi section extracted")
    
    # Parse kualifikasi
    parsed_data = parse_kualifikasi(kualifikasi_text)
    
    print("\n" + "="*70)
    print("EXTRACTED INFORMATION")
    print("="*70)
    print(f"Gender: {parsed_data['gender'] or 'Not specified'}")
    print(f"Age Range: {parsed_data['age_range'] or 'Not specified'}")
    print(f"Education: {', '.join(parsed_data['education']) or 'Not specified'}")
    print(f"Location: {parsed_data['location'] or 'Not specified'}")
    print(f"Min Experience: {parsed_data['min_experience_years']} years")
    print(f"Experience Keywords: {', '.join(parsed_data['experience_keywords']) or 'None found'}")
    print(f"Skills: {', '.join(parsed_data['skills']) or 'None found'}")
    
    # Get position title
    print("\n" + "="*70)
    position = input("Position Title: ").strip()
    if not position:
        print("Error: Position title is required!")
        return
    
    # Confirm or edit
    print("\nPress Enter to use extracted values, or type new value:")
    
    gender_input = input(f"Gender [{parsed_data['gender'] or 'None'}]: ").strip()
    if gender_input:
        parsed_data['gender'] = gender_input if gender_input.lower() != 'none' else None
    
    location_input = input(f"Location [{parsed_data['location'] or 'None'}]: ").strip()
    if location_input:
        parsed_data['location'] = location_input if location_input.lower() != 'none' else None
    
    age_input = input(f"Age Range [{parsed_data['age_range'] or 'None'}]: ").strip()
    if age_input and age_input.lower() != 'none':
        if '-' in age_input:
            min_age, max_age = age_input.split('-')
            parsed_data['age_range'] = {'min': int(min_age.strip()), 'max': int(max_age.strip())}
    
    exp_input = input(f"Min Experience Years [{parsed_data['min_experience_years']}]: ").strip()
    if exp_input:
        parsed_data['min_experience_years'] = int(exp_input)
    
    # Build requirements JSON
    requirements = build_requirements_json(parsed_data, position, kualifikasi_text)
    
    # Save
    filename_slug = position.lower().replace(' ', '_').replace('/', '_')
    filename_slug = re.sub(r'[^a-z0-9_]', '', filename_slug)
    default_filename = f"{filename_slug}.json"
    
    filename = input(f"\nSave as (default: {default_filename}): ").strip()
    if not filename:
        filename = default_filename
    
    if not filename.endswith('.json'):
        filename += '.json'
    
    filepath = Path('requirements') / filename
    filepath.parent.mkdir(exist_ok=True)
    
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(requirements, f, indent=2, ensure_ascii=False)
    
    print(f"\n✓ Requirements saved to: {filepath}")
    print("\nPreview:")
    print(json.dumps(requirements, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
