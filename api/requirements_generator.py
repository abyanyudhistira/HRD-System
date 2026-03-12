"""
Requirements Generator - Generate Checklist Format Requirements
UPDATED: Now uses new checklist format compatible with new scoring system
Usage: python requirements_generator.py
"""
import json
import re
from pathlib import Path


def clean_html(text):
    """Remove HTML tags from text"""
    text = re.sub(r'<[^>]+>', '', text)
    text = re.sub(r'\s+', ' ', text)
    text = text.replace('&nbsp;', ' ').replace('&amp;', '&')
    text = text.replace('&lt;', '<').replace('&gt;', '>')
    text = text.replace('&quot;', '"')
    return text.strip()


def extract_bullet_points(text):
    """Extract bullet points from text"""
    if not text:
        return []
    
    bullets = []
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    
    # Remove heading line if present
    if lines and any(keyword in lines[0].lower() for keyword in ['kualifikasi', 'persyaratan', 'requirements', 'syarat']):
        lines = lines[1:]
    
    for line in lines:
        # Skip if too short
        if len(line) < 5:
            continue
        
        # Clean bullet markers
        line_clean = re.sub(r'^[•\-\*○\d+\.\)]\s*', '', line).strip()
        
        if line_clean and len(line_clean) >= 5:
            bullets.append(line_clean)
    
    return bullets


def classify_requirement(text, req_id):
    """Classify a single requirement and extract structured value"""
    text_lower = text.lower()
    
    # Priority 1: Gender
    if any(word in text_lower for word in ['pria', 'wanita', 'laki-laki', 'perempuan', 'male', 'female']):
        # Determine gender value
        if 'pria / wanita' in text_lower or 'pria/wanita' in text_lower or ('pria' in text_lower and 'wanita' in text_lower):
            gender_value = 'any'
        elif any(word in text_lower for word in ['wanita', 'perempuan', 'female']):
            gender_value = 'female'
        elif any(word in text_lower for word in ['pria', 'laki-laki', 'male']):
            gender_value = 'male'
        else:
            gender_value = 'any'
        
        return {
            'id': 'gender',
            'type': 'gender',
            'label': text,
            'value': gender_value
        }
    
    # Priority 2: Age
    if any(word in text_lower for word in ['usia', 'umur', 'age']):
        # Extract age range
        age_patterns = [
            r'(\d+)\s*-\s*(\d+)\s*tahun',
            r'(\d+)\s*sampai\s*(\d+)\s*tahun',
            r'maksimal\s*(\d+)\s*tahun',
            r'max\s*(\d+)\s*tahun'
        ]
        
        age_value = {'min': 18, 'max': 35}  # default
        
        for pattern in age_patterns:
            match = re.search(pattern, text_lower)
            if match:
                if match.lastindex >= 2:
                    age_value = {
                        'min': int(match.group(1)),
                        'max': int(match.group(2))
                    }
                else:
                    age_value = {
                        'min': 18,
                        'max': int(match.group(1))
                    }
                break
        
        return {
            'id': 'age_range',
            'type': 'age',
            'label': text,
            'value': age_value
        }
    
    # Priority 3: Education - FIXED DETECTION (more specific keywords)
    education_keywords = ['pendidikan', 'education', 'lulusan', 'ijazah', 'degree', 'bachelor', 'master', 'phd', 'sarjana', 's1', 's-1', 's2', 's-2', 'diploma', 'd3', 'd-3', 'sma', 'smk', 'slta']
    if any(word in text_lower for word in education_keywords):
        # Determine education level
        if any(word in text_lower for word in ['bachelor', 'sarjana', 's1', 's-1']) or 'bachelor degree' in text_lower:
            edu_value = 'bachelor'
        elif any(word in text_lower for word in ['master', 's2', 's-2']):
            edu_value = 'master'
        elif any(word in text_lower for word in ['diploma', 'd3', 'd-3']):
            edu_value = 'diploma'
        elif any(word in text_lower for word in ['sma', 'smk', 'high school', 'slta']):
            edu_value = 'high school'
        elif 'degree' in text_lower:  # Any degree mention defaults to bachelor
            edu_value = 'bachelor'
        else:
            edu_value = 'bachelor'  # default for education mentions
        
        return {
            'id': 'education',
            'type': 'education',
            'label': text,
            'value': edu_value
        }
    
    # Priority 4: Location
    if any(word in text_lower for word in ['penempatan', 'lokasi', 'domisili', 'location', 'ditempatkan']):
        # Extract location name
        location_match = re.search(r'(?:penempatan|lokasi|domisili|location|ditempatkan)\s*:?\s*([A-Za-z\s]+)', text, re.IGNORECASE)
        if location_match:
            location_value = location_match.group(1).strip()
            # Remove trailing words like "atau", "dan"
            location_value = re.sub(r'\s+(atau|or|dan|and)\s+.*', '', location_value, flags=re.IGNORECASE).strip()
        else:
            location_value = 'any'
        
        return {
            'id': 'location',
            'type': 'location',
            'label': text,
            'value': location_value.lower()
        }
    
    # Priority 5: Experience (with years) - FIXED DETECTION
    if any(word in text_lower for word in ['pengalaman', 'experience', 'berpengalaman', 'years', 'tahun']):
        # Extract years - FIXED PATTERNS (more specific order)
        exp_patterns = [
            r'(\d+)\+?\s*years?\s+experience',  # "5+ years experience" - most specific first
            r'(\d+)\+?\s*years?\s+of\s+experience',  # "5+ years of experience"
            r'experience.*?(\d+)\+?\s*years?',  # "experience with 5+ years"
            r'(\d+)\+?\s*years?\s+(?:pengalaman|experience)',  # "5+ years pengalaman"
            r'(?:minimal|minimum|min\.?)\s*(\d+)\s*(?:tahun|years?)',  # "minimum 5 years"
            r'(\d+)\s*(?:tahun|years?)\s*(?:pengalaman|experience)',  # "5 tahun pengalaman"
            r'(\d+)\+?\s*(?:tahun|years?)',  # "5+ years" - least specific last
        ]
        
        exp_value = 1  # default
        
        for pattern in exp_patterns:
            match = re.search(pattern, text_lower)
            if match:
                exp_value = int(match.group(1))
                break
        
        return {
            'id': 'min_experience',
            'type': 'experience',
            'label': text,
            'value': exp_value
        }
    
    # Default: Skill - generate descriptive ID from label
    # Clean the text to create a skill ID
    skill_text = text_lower
    # Remove common prefixes
    skill_text = re.sub(r'^(must have|nice to have|strong|good|excellent|proficiency in|experience with|knowledge of|familiar with|understanding of)[\s:]+', '', skill_text)
    # Take first few words and clean
    skill_words = skill_text.split()[:3]  # Take max 3 words
    skill_id = '_'.join(skill_words)
    # Clean special characters
    skill_id = re.sub(r'[^\w\s]', '', skill_id)
    skill_id = re.sub(r'\s+', '_', skill_id)
    skill_id = f'skill_{skill_id}'
    
    return {
        'id': skill_id,
        'type': 'skill',
        'label': text,
        'value': text.lower()
    }


def generate_requirements_from_text(job_description, position_title):
    """Generate requirements in new checklist format"""
    
    # Extract bullet points
    bullets = extract_bullet_points(job_description)
    
    # Classify each bullet point
    requirements_array = []
    
    # Track counts for generating unique IDs
    type_counts = {
        'experience': 0,
        'skill': 0,
        'education': 0,
        'gender': 0,
        'age': 0,
        'location': 0
    }
    
    for i, bullet in enumerate(bullets):
        req = classify_requirement(bullet, i + 1)
        
        # Make IDs unique by adding counter for types that can appear multiple times
        req_type = req['type']
        
        if req_type in ['experience', 'skill']:
            type_counts[req_type] += 1
            
            # For experience: use min_experience, experience_2, experience_3, etc
            if req_type == 'experience':
                if type_counts[req_type] == 1:
                    req['id'] = 'min_experience'
                else:
                    req['id'] = f'experience_{type_counts[req_type]}'
            
            # For skill: keep the descriptive ID but ensure uniqueness
            elif req_type == 'skill':
                # ID already generated in classify_requirement, just ensure it's unique
                base_id = req['id']
                # Check if this ID already exists
                existing_ids = [r['id'] for r in requirements_array]
                if base_id in existing_ids:
                    req['id'] = f"{base_id}_{type_counts[req_type]}"
        
        requirements_array.append(req)
    
    # Add default requirements if none found
    if len(requirements_array) == 0:
        requirements_array = [
            {
                'id': 'min_experience',
                'type': 'experience',
                'label': 'Minimum 1 year experience',
                'value': 1
            },
            {
                'id': 'education',
                'type': 'education',
                'label': 'Education: High School',
                'value': 'high school'
            }
        ]
    
    # Build final output
    return {
        'position': position_title,
        'requirements': requirements_array
    }


def main():
    print("="*70)
    print("REQUIREMENTS GENERATOR - New Checklist Format")
    print("="*70)
    print("\nGenerate requirements from job description")
    print("Output format: Checklist array for new scoring system\n")
    
    # Get position title
    position = input("Position Title: ").strip()
    if not position:
        print("Error: Position title is required!")
        return
    
    # Get job description
    print("\nPaste job description (press Ctrl+D or Ctrl+Z when done):")
    print("-" * 70)
    
    lines = []
    try:
        while True:
            line = input()
            lines.append(line)
    except EOFError:
        pass
    
    job_description = '\n'.join(lines)
    
    if not job_description.strip():
        print("\nError: Job description is required!")
        return
    
    # Generate requirements
    print("\n" + "="*70)
    print("GENERATING REQUIREMENTS...")
    print("="*70)
    
    requirements = generate_requirements_from_text(job_description, position)
    
    # Display result
    print("\n" + "="*70)
    print("GENERATED REQUIREMENTS (Checklist Format)")
    print("="*70)
    print(json.dumps(requirements, indent=2, ensure_ascii=False))
    print("="*70)
    print(f"\nTotal requirements: {len(requirements['requirements'])}")
    
    # Save to file
    filename_slug = position.lower().replace(' ', '_').replace('-', '_')
    filename_slug = ''.join(c for c in filename_slug if c.isalnum() or c == '_')
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
    
    print(f"\n✓ Saved to: {filepath}")
    print("\nYou can now use this requirements file for scoring!")


if __name__ == "__main__":
    main()