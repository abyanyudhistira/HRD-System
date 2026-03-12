"""
Quick Requirements Generator - Simplified version
Usage: python quick_requirements.py "job_description.txt"
"""
import json
import sys
import re
from pathlib import Path


# Template requirements untuk berbagai posisii
TEMPLATES = {
    "desk_collection": {
        "required_experience_keywords": [
            "Desk Collection", "Call Collection", "Telecollection",
            "Debt Collection", "Collection", "Penagihan", "Collector"
        ],
        "preferred_experience_keywords": [
            "BPR", "Bank Perkreditan Rakyat", "Lembaga Keuangan",
            "Financial Institution", "Banking", "Finance"
        ],
        "required_skills": {
            "Communication": 10, "Negotiation": 10, "Customer Service": 8,
            "Persuasion": 8, "Microsoft Office": 5
        },
        "preferred_skills": {
            "Problem Solving": 7, "Target Oriented": 7, "Sales": 6
        }
    },
    "backend_developer": {
        "required_experience_keywords": [
            "Backend Developer", "Backend Engineer", "Software Engineer",
            "Developer", "Programmer"
        ],
        "preferred_experience_keywords": [
            "Senior", "Lead", "Tech Lead", "Startup", "Tech Company"
        ],
        "required_skills": {
            "Python": 10, "Java": 8, "Node.js": 8, "SQL": 9,
            "REST API": 9, "Git": 7, "Linux": 6
        },
        "preferred_skills": {
            "Docker": 7, "Kubernetes": 6, "AWS": 8, "Redis": 6,
            "MongoDB": 5, "Microservices": 7
        }
    },
    "frontend_developer": {
        "required_experience_keywords": [
            "Frontend Developer", "Frontend Engineer", "UI Developer",
            "Web Developer"
        ],
        "preferred_experience_keywords": [
            "Senior", "Lead", "Startup", "Tech Company"
        ],
        "required_skills": {
            "JavaScript": 10, "React": 9, "HTML": 8, "CSS": 8,
            "TypeScript": 7, "Git": 7
        },
        "preferred_skills": {
            "Next.js": 7, "Vue.js": 6, "Angular": 6, "Tailwind": 5,
            "Redux": 5, "Webpack": 4
        }
    },
    "data_scientist": {
        "required_experience_keywords": [
            "Data Scientist", "Data Analyst", "Machine Learning Engineer",
            "AI Engineer"
        ],
        "preferred_experience_keywords": [
            "Senior", "Lead", "Research", "PhD"
        ],
        "required_skills": {
            "Python": 10, "Machine Learning": 10, "Statistics": 9,
            "SQL": 8, "Pandas": 8, "NumPy": 7
        },
        "preferred_skills": {
            "TensorFlow": 8, "PyTorch": 8, "Deep Learning": 7,
            "NLP": 6, "Computer Vision": 6, "Big Data": 5
        }
    }
}


def quick_generate(template_name, position, min_exp=1, gender=None, location=None, age_range=None):
    """Quick generate requirements from template"""
    
    if template_name not in TEMPLATES:
        print(f"Error: Template '{template_name}' not found!")
        print(f"Available templates: {', '.join(TEMPLATES.keys())}")
        return None
    
    template = TEMPLATES[template_name]
    
    requirements = {
        "position": position,
        "job_description": f"Position for {position}",
        "min_experience_years": min_exp,
        "required_experience_keywords": template["required_experience_keywords"],
        "preferred_experience_keywords": template["preferred_experience_keywords"],
        "required_skills": template["required_skills"],
        "preferred_skills": template["preferred_skills"],
        "education_level": ["High School", "Diploma", "Bachelor"]
    }
    
    if gender:
        requirements["required_gender"] = gender
    
    if location:
        requirements["required_location"] = location
    
    if age_range:
        requirements["required_age_range"] = age_range
    
    return requirements


def main():
    print("="*70)
    print("QUICK REQUIREMENTS GENERATOR")
    print("="*70)
    
    print("\nAvailable templates:")
    for i, template_name in enumerate(TEMPLATES.keys(), 1):
        print(f"  {i}. {template_name}")
    
    # Select template
    template_choice = input("\nSelect template (1-{}): ".format(len(TEMPLATES))).strip()
    try:
        template_idx = int(template_choice) - 1
        template_name = list(TEMPLATES.keys())[template_idx]
    except (ValueError, IndexError):
        print("Invalid choice!")
        return
    
    # Input details
    position = input("\nPosition Title: ").strip()
    if not position:
        print("Error: Position title is required!")
        return
    
    min_exp = input("Minimum Experience Years (default: 1): ").strip()
    min_exp = int(min_exp) if min_exp else 1
    
    gender = input("Required Gender (Male/Female/None): ").strip()
    gender = gender if gender and gender.lower() != 'none' else None
    
    location = input("Required Location (or None): ").strip()
    location = location if location and location.lower() != 'none' else None
    
    age_input = input("Age Range (format: 20-35, or None): ").strip()
    age_range = None
    if age_input and age_input.lower() != 'none' and '-' in age_input:
        try:
            min_age, max_age = age_input.split('-')
            age_range = {"min": int(min_age.strip()), "max": int(max_age.strip())}
        except:
            pass
    
    # Generate
    requirements = quick_generate(
        template_name, position, min_exp, gender, location, age_range
    )
    
    if not requirements:
        return
    
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
