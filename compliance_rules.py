"""
Compliance rules for Sequis Asset Management Individual Account Opening Form.
Defines required fields, their expected patterns, and page locations.
"""

# Required fields on Page 1 (Cover Page)
PAGE_1_REQUIRED = [
    "Nomor SID",
    "Kode Nasabah",
    "Nama Nasabah",
]

# Required fields on Page 2 (Personal Data — fields marked with * in the form)
PAGE_2_REQUIRED_FIELDS = [
    {"key": "Nama Lengkap", "label": "Full Name", "pattern": r"###\s*1\.\s*Nama Lengkap.*\n\n(.+)"},
    {"key": "Tempat & Tanggal Lahir", "label": "Place & Date of Birth", "pattern": r"###\s*3\.\s*Tempat.*Tanggal Lahir.*\n\n(.+)"},
    {"key": "Nama Ibu Kandung", "label": "Mother's Maiden Name", "pattern": r"###\s*4\.\s*Nama Ibu Kandung.*\n\n(.+)"},
    {"key": "Jenis Kelamin", "label": "Sex", "pattern": r"###\s*5\.\s*Jenis Kelamin.*\n\n(.+)"},
    {"key": "Nomor Kartu Identitas", "label": "ID Number (KTP)", "pattern": r"###\s*6\.\s*Nomor Kartu Identitas.*\n\n(.+)"},
    {"key": "Kewarganegaraan", "label": "Nationality", "pattern": r"###\s*7\.\s*Kewarganegaraan.*\n\n(.+)"},
    {"key": "Alamat Sesuai Identitas", "label": "Address (ID Card)", "pattern": r"###\s*9\.\s*Alamat Sesuai.*\n\n(.+)"},
    {"key": "Kota", "label": "City", "pattern": r"(?:\*\*)?Kota\*[^\n]*(?:\*\*)?[^\n]*\n([^\n]+)"},
    {"key": "Provinsi", "label": "Province", "pattern": r"(?:\*\*)?Provinsi\*[^\n]*(?:\*\*)?[^\n]*\n([^\n]+)"},
    {"key": "Kode Pos", "label": "Postal Code", "pattern": r"(?:\*\*)?Kode Pos\*[^\n]*(?:\*\*)?[^\n]*\n([^\n]+)"},
    {"key": "Email", "label": "Email", "pattern": r"###\s*12\.\s*Email.*\n\n(.+)"},
    {"key": "Status Perkawinan", "label": "Marital Status", "pattern": r"###\s*15\.\s*Status Perkawinan.*\n\n(.+)"},
    {"key": "Pekerjaan", "label": "Occupation", "pattern": r"###\s*16\.\s*Pekerjaan.*\n\n(.+)"},
]

# Fields that require at least one checkbox selected (radio-button groups)
REQUIRED_SELECTIONS = [
    {"key": "Jenis Kelamin", "options": ["Laki-Laki", "Perempuan"]},
    {"key": "Kewarganegaraan", "options": ["WNI", "WNA"]},
    {"key": "Status Perkawinan", "options": ["Belum Menikah", "Menikah", "Cerai"]},
    {"key": "Latar Belakang Pendidikan", "options": ["SMA", "S1", "S2", "S3", "Lainnya"]},
    {"key": "Agama", "options": ["Islam", "Protestant", "Katolik", "Konghucu", "Budha", "Hindu", "Lainnya"]},
]

# Page 4 requirements
PAGE_4_REQUIRED = [
    {"key": "Tanggal", "label": "Date", "pattern": r"\*\*Tanggal/bulan/tahun\s*:?\*\*\s*(.+)"},
    {"key": "Tanda Tangan", "label": "Client Signature", "pattern": r"Tanda Tangan Nasabah"},
    {"key": "KTP Copy", "label": "KTP/Passport Copy Attached", "pattern": r"☑.*KTP|☑.*Paspor"},
]

# Page 5 — Investor Profile (at least some answers expected)
PAGE_5_MINIMUM_ANSWERS = 3

# Page 7 — Beneficial Owner
# NOTE: BO fields are on single lines like "**Nama Beneficial Owner (BO)** : value"
# Use [^\n]* patterns throughout — \s* crosses newlines and captures the next field.
PAGE_7_REQUIRED = [
    {"key": "Nama Beneficial Owner", "label": "BO Name", "pattern": r"\*\*Nama Beneficial Owner[^\n]*\*\*[^\n]*:([^\n]+)"},
    {"key": "Hubungan BO", "label": "BO Relationship", "pattern": r"\*\*Hubungan BO[^\n]*\*\*[^\n]*:([^\n]+)"},
    {"key": "Tempat & Tanggal Lahir BO", "label": "BO Birth", "pattern": r"\*\*Tempat[^\n]*Tanggal Lahir BO[^\n]*\*\*[^\n]*:([^\n]+)"},
    {"key": "No. Identitas BO", "label": "BO ID Number", "pattern": r"\*\*No\.\s*Identitas BO[^\n]*\*\*[^\n]*:([^\n]+)"},
    {"key": "Alamat Lengkap BO", "label": "BO Address", "pattern": r"\*\*Alamat Lengkap BO[^\n]*\*\*[^\n]*:([^\n]+)"},
]
