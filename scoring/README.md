# Profile Scoring System

Sistem scoring otomatis untuk mencocokkan profile LinkedIn dengan job requirements menggunakan **Hybrid Scoring Method**:
- ✅ Keyword Matching + Fuzzy String Matching
- ✅ TF-IDF + Cosine Similarity
- ✅ Experience Years Calculation
- ✅ Education Level Matching

## Features

### 1. Skills Matching (40 points)
- **Required Skills (30 pts)**: Skills yang wajib dimiliki
- **Preferred Skills (10 pts)**: Skills tambahan yang diinginkan
- **Fuzzy Matching**: Mendeteksi variasi penulisan (PostgreSQL = Postgres, React.js = ReactJS)
- **Weighted Scoring**: Setiap skill punya bobot berbeda

### 2. Text Similarity (30 points)
- **TF-IDF Vectorization**: Mengubah text menjadi vector
- **Cosine Similarity**: Mengukur kesamaan job description dengan profile
- Membandingkan: job description vs (about + experiences + projects)

### 3. Experience (20 points)
- Menghitung total tahun pengalaman dari semua posisi
- Parsing duration format: "2 yrs 3 mos", "6 mos", dll
- Full points jika memenuhi minimum requirement

### 4. Education (10 points)
- Matching education level dengan requirement
- Hierarchy: High School < Diploma < Bachelor < Master < PhD
- Partial points jika level lebih rendah dari requirement

## Setup

### 1. Create Virtual Environment (Linux)

```bash
cd scoring

# Create venv
python3 -m venv venv

# Activate venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

**Dependencies:**
- `pika`: RabbitMQ client
- `rapidfuzz`: Fuzzy string matching
- `scikit-learn`: TF-IDF & Cosine Similarity
- `numpy`: Numerical operations

**Note:** Setiap kali mau run script, activate venv dulu:
```bash
source venv/bin/activate
```

### 2. Prepare Requirements Files

Buat file JSON di folder `requirements/` untuk setiap posisi:

```json
{
  "position": "Backend Developer",
  "job_description": "Job description text here...",
  "required_skills": {
    "Python": 10,
    "FastAPI": 8,
    "PostgreSQL": 7
  },
  "preferred_skills": {
    "Docker": 6,
    "Redis": 5
  },
  "min_experience_years": 3,
  "education_level": ["Bachelor", "Master"]
}
```

**Contoh requirements sudah tersedia:**
- `backend_dev_senior.json`
- `frontend_dev.json`
- `fullstack_dev.json`
- `data_scientist.json`
- `devops_engineer.json`

### 3. Configure LavinMQ

Setup LavinMQ credentials in `.env`:

```bash
cp .env.example .env
# Edit .env with your LavinMQ credentials
# See ../../LAVINMQ-SETUP.md for detailed setup guide
```

Test connection:
```bash
cd ../..
python test-lavinmq.py
```

## Usage

**IMPORTANT:** Activate venv sebelum run script apapun:
```bash
source venv/bin/activate
```

### Mode 1: Test Scoring (Tanpa RabbitMQ)

Test scoring system dengan sample data:

```bash
python test_scorer.py
```

Output:
```
SCORE RESULT
============================================================
Total Score: 85.5/100
Percentage: 85.5%
Recommendation: Highly Recommended - Strong match

BREAKDOWN
------------------------------------------------------------
1. Skills: 35.2/40
   Required: 27.5/30
   - Matched: 8 skills
   Preferred: 7.7/10
   - Matched: 4 skills

2. Text Similarity: 24.3/30
   Similarity: 81.0%

3. Experience: 20.0/20
   Total years: 4.8 years
   Required: 3 years

4. Education: 10.0/10
   Degrees: Bachelor of Computer Science
```

### Mode 2: RabbitMQ Consumer (Production)

Start scoring workers yang listen ke RabbitMQ:

```bash
python scoring_consumer.py
```

**Input:**
```
Number of workers (default 2): 3
```

**Output:**
```
PROFILE SCORING CONSUMER
============================================================

✓ Found 5 requirements file(s):
  - backend_dev_senior.json
  - frontend_dev.json
  - fullstack_dev.json
  - data_scientist.json
  - devops_engineer.json

→ Configuration:
  - RabbitMQ: localhost:5672
  - Queue: scoring_queue
  - Workers: 3
  - Output: data/scores/

✓ Connected to RabbitMQ
  - Messages in queue: 0

✓ All 3 workers are running!
  Waiting for messages from crawler...

[Worker 1] Started
[Worker 2] Started
[Worker 3] Started
```

Workers akan otomatis process message dari crawler!

## Integration dengan Crawler

### Flow Lengkap:

```
1. Crawler scrape profile → Save JSON
2. Crawler send message ke RabbitMQ queue: "scoring_queue"
3. Scoring consumer receive message → Process scoring
4. Save result ke: data/scores/
5. Update Supabase leads_list table with score
```

### Supabase Score Updates

The scoring consumer automatically updates the `leads_list` table in Supabase with scoring results:

**Behavior:**
- **Always overwrites** existing scores with new scores
- Updates `scored_at` timestamp to current date on every scoring run
- Preserves existing `profile_data` if already present
- Adds `profile_data` if not yet in database

**Example Output:**
```
✓ Supabase updated: https://linkedin.com/in/johndoe → score: 75.5 → 85.5 (overwritten)
✓ Supabase updated: https://linkedin.com/in/janedoe → score: 82.0 (new)
```

**Use Cases:**
- Re-scoring profiles with updated requirements
- Correcting scores after requirement adjustments
- Batch re-scoring of existing leads

**Note:** This allows you to refine your requirements and re-score profiles without worrying about stale scores in the database.

### Message Format:

```json
{
  "profile_data": {
    "name": "John Doe",
    "skills": ["Python", "FastAPI"],
    "experiences": [...],
    "education": [...],
    "about": "..."
  },
  "requirements_id": "backend_dev_senior",
  "profile_url": "https://linkedin.com/in/johndoe"
}
```

## Output

Hasil scoring disimpan di `data/scores/` dengan format:

```
data/scores/john_doe_backend_dev_senior_20240209_143022_score.json
```

**Content:**
```json
{
  "profile": {
    "name": "John Doe",
    "skills": [...],
    ...
  },
  "requirements_id": "backend_dev_senior",
  "score": {
    "total_score": 85.5,
    "max_score": 100,
    "percentage": 85.5,
    "recommendation": "Highly Recommended - Strong match",
    "breakdown": {
      "skills": {...},
      "text_similarity": {...},
      "experience": {...},
      "education": {...}
    }
  },
  "scored_at": "2024-02-09T14:30:22"
}
```

## Score Interpretation

| Score | Recommendation | Meaning |
|-------|---------------|---------|
| 80-100 | Highly Recommended | Strong match, proceed to interview |
| 60-79 | Recommended | Good match, consider for interview |
| 40-59 | Consider | Moderate match, review carefully |
| 0-39 | Not Recommended | Weak match, likely not suitable |

## Customization

### Adjust Scoring Weights

Edit `scorer.py` untuk mengubah bobot:

```python
# Current weights:
# Skills: 40 points (30 required + 10 preferred)
# Text Similarity: 30 points
# Experience: 20 points
# Education: 10 points

# Contoh: Jika ingin skills lebih penting
skills_score = self._score_skills(...) * 1.5  # 60 points
text_score = self._score_text_similarity(...) * 0.5  # 15 points
```

### Add New Requirements

Buat file JSON baru di `requirements/`:

```bash
cp requirements/backend_dev_senior.json requirements/my_position.json
# Edit my_position.json
```

### Fuzzy Matching Threshold

Edit `scorer.py` line ~80:

```python
if ratio >= 80:  # Change threshold (0-100)
```

- **80-90**: Strict matching
- **70-80**: Moderate (recommended)
- **60-70**: Loose matching

## Troubleshooting

### Error: "No module named 'pika'"
```bash
# Activate venv first!
source venv/bin/activate

# Then install
pip install -r requirements.txt
```

### Error: "externally-managed-environment" (Linux)
```bash
# Jangan install global, pakai venv!
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Error: "Failed to connect to RabbitMQ/LavinMQ"
```bash
# Test LavinMQ connection
cd ../..
python test-lavinmq.py

# Check .env credentials
cat .env | grep RABBITMQ

# Pastikan RABBITMQ_VHOST sudah diset!
```

### Error: "Requirements file not found"
```bash
# Check files
ls requirements/

# Create if missing
mkdir -p requirements
```

### Low Scores for Good Candidates

1. **Check skill names**: Pastikan nama skill di requirements match dengan LinkedIn
2. **Add job description**: Text similarity butuh job description yang detail
3. **Adjust fuzzy threshold**: Lower threshold untuk matching lebih loose
4. **Check requirements**: Mungkin requirements terlalu strict

## Monitoring

### RabbitMQ Management UI

```
http://localhost:15672
Username: guest
Password: guest
```

- Monitor queue size
- Check message rate
- View consumer connections

### Statistics

Scoring consumer menampilkan stats real-time:

```
SCORING STATISTICS
============================================================
Processing: 2
Completed: 15
Failed: 1
Skipped (duplicates): 3
Supabase Updated: 12
Supabase Failed: 0
Success Rate: 93.8%
============================================================
```

**Statistics Breakdown:**
- **Processing**: Currently being scored
- **Completed**: Successfully scored and saved
- **Failed**: Scoring errors
- **Skipped**: Already scored (duplicate prevention for file output)
- **Supabase Updated**: Successfully updated in database (includes overwrites)
- **Supabase Failed**: Database update failures

## Next Steps

### Setup (Manual):
```bash
cd scoring
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
mkdir -p data/scores
```

### Test:
```bash
source venv/bin/activate
python test_scorer.py
```

### Run Consumer:
```bash
source venv/bin/activate
python scoring_consumer.py
```

### Deactivate venv:
```bash
deactivate
```

## Questions?

Jika ada pertanyaan atau butuh customize lebih lanjut, silakan tanya! 🚀
