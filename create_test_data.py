"""
Generates test datasets strictly in data/test/ for testing all 10 test cases.
Uses clean TrueType typography for realistic marksheet OCR rendering.
"""
import os
import pandas as pd
from PIL import Image, ImageDraw, ImageFont


def get_font(size: int):
    font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    if os.path.exists(font_path):
        return ImageFont.truetype(font_path, size)
    return ImageFont.load_default()


def generate_test_files():
    os.makedirs("data/test", exist_ok=True)
    os.makedirs("reports", exist_ok=True)

    # 1. Official College Records Ground Truth
    official_data = [
        {"Roll Number": "101", "Student Name": "Rahul Patil", "CGPA": 8.25},
        {"Roll Number": "102", "Student Name": "Priya Sharma", "CGPA": 9.10},
        {"Roll Number": "103", "Student Name": "Amit Verma", "CGPA": 7.80},
        {"Roll Number": "104", "Student Name": "Sneha Deshmukh", "CGPA": 8.95},
        {"Roll Number": "105", "Student Name": "Rohit Kulkarni", "CGPA": 6.75},
        {"Roll Number": "106", "Student Name": "Anjali Gupta", "CGPA": 8.50}
    ]
    df_official = pd.DataFrame(official_data)
    official_path = "data/test/official_college_records_sample.xlsx"
    df_official.to_excel(official_path, index=False)
    print(f"Generated {official_path}")

    # 2. Student Submitted Records (covers test cases 1 to 5)
    submitted_data = [
        # Case 1: Correct student data (matches 101 perfectly)
        {"Roll Number": "101", "Student Name": "Rahul Patil", "CGPA": 8.25},
        
        # Case 2: Incorrect CGPA (Inflated CGPA 9.80 vs official 9.10)
        {"Roll Number": "102", "Student Name": "Priya Sharma", "CGPA": 9.80},
        
        # Case 3: Incorrect name (Impersonator name vs official Amit Verma)
        {"Roll Number": "103", "Student Name": "Vikram Singh", "CGPA": 7.80},
        
        # Case 4: Transposed name but wrong CGPA
        {"Roll Number": "104", "Student Name": "Deshmukh Sneha", "CGPA": 9.60},
        
        # Case 5: Roll Number not found in official college database
        {"Roll Number": "999", "Student Name": "Rajat Kapoor", "CGPA": 8.40}
    ]
    df_submitted = pd.DataFrame(submitted_data)
    submitted_path = "data/test/student_submitted_records_sample.xlsx"
    df_submitted.to_excel(submitted_path, index=False)
    print(f"Generated {submitted_path}")

    # 3. Generate Marksheet Images for OCR Testing (Cases 6, 7, 8)
    title_font = get_font(24)
    subtitle_font = get_font(18)
    body_font = get_font(20)
    bold_font = get_font(22)
    
    # Case 6: OCR Correct Marksheet (Roll 101, Rahul Patil, CGPA: 8.25)
    img_correct = Image.new('RGB', (1000, 750), color=(255, 255, 255))
    draw = ImageDraw.Draw(img_correct)
    draw.rectangle([30, 30, 970, 720], outline=(0, 0, 0), width=4)
    draw.rectangle([36, 36, 964, 714], outline=(100, 100, 100), width=1)
    
    draw.text((220, 60), "STATE INSTITUTE OF TECHNOLOGY & SCIENCE", fill=(0, 0, 0), font=title_font)
    draw.text((320, 100), "OFFICIAL GRADE REPORT & MARKSHEET", fill=(0, 0, 0), font=subtitle_font)
    draw.line([(60, 140), (940, 140)], fill=(0, 0, 0), width=2)
    
    draw.text((80, 180), "Student Name: Rahul Patil", fill=(0, 0, 0), font=body_font)
    draw.text((80, 240), "Roll Number: 101", fill=(0, 0, 0), font=body_font)
    draw.text((80, 300), "Academic Program: Bachelor of Technology (B.Tech)", fill=(0, 0, 0), font=body_font)
    draw.text((80, 360), "Department: Computer Science and Engineering", fill=(0, 0, 0), font=body_font)
    draw.text((80, 420), "Semester: VIII", fill=(0, 0, 0), font=body_font)
    draw.line([(60, 470), (940, 470)], fill=(0, 0, 0), width=1)
    
    draw.text((80, 510), "Cumulative Grade Point Average (CGPA): 8.25", fill=(0, 0, 0), font=bold_font)
    draw.text((80, 570), "Result: FIRST CLASS WITH DISTINCTION", fill=(0, 0, 0), font=body_font)
    draw.text((650, 650), "Controller of Examinations", fill=(0, 0, 0), font=body_font)
    img_correct.save("data/test/marksheet_case6_correct.png")
    print("Generated data/test/marksheet_case6_correct.png")

    # Case 7: OCR Incorrect/Mismatched Marksheet (Forged CGPA 9.95 vs official 8.25)
    img_mismatch = Image.new('RGB', (1000, 750), color=(255, 255, 255))
    draw = ImageDraw.Draw(img_mismatch)
    draw.rectangle([30, 30, 970, 720], outline=(0, 0, 0), width=4)
    draw.rectangle([36, 36, 964, 714], outline=(100, 100, 100), width=1)
    
    draw.text((220, 60), "STATE INSTITUTE OF TECHNOLOGY & SCIENCE", fill=(0, 0, 0), font=title_font)
    draw.text((320, 100), "OFFICIAL GRADE REPORT & MARKSHEET", fill=(0, 0, 0), font=subtitle_font)
    draw.line([(60, 140), (940, 140)], fill=(0, 0, 0), width=2)
    
    draw.text((80, 180), "Student Name: Rahul Patil", fill=(0, 0, 0), font=body_font)
    draw.text((80, 240), "Roll Number: 101", fill=(0, 0, 0), font=body_font)
    draw.text((80, 300), "Academic Program: Bachelor of Technology (B.Tech)", fill=(0, 0, 0), font=body_font)
    draw.text((80, 360), "Department: Computer Science and Engineering", fill=(0, 0, 0), font=body_font)
    draw.text((80, 420), "Semester: VIII", fill=(0, 0, 0), font=body_font)
    draw.line([(60, 470), (940, 470)], fill=(0, 0, 0), width=1)
    
    draw.text((80, 510), "Cumulative Grade Point Average (CGPA): 9.95", fill=(0, 0, 0), font=bold_font)
    draw.text((80, 570), "Result: FIRST CLASS WITH DISTINCTION", fill=(0, 0, 0), font=body_font)
    draw.text((650, 650), "Controller of Examinations", fill=(0, 0, 0), font=body_font)
    img_mismatch.save("data/test/marksheet_case7_mismatch.png")
    print("Generated data/test/marksheet_case7_mismatch.png")

    # Case 8: OCR Unreadable/Damaged Marksheet (Blurry / Dark Noise / Unparseable)
    img_unreadable = Image.new('RGB', (800, 600), color=(15, 15, 15))
    draw = ImageDraw.Draw(img_unreadable)
    draw.text((100, 300), "~~~~~~ %%%%% @@@@@@ ^^^^^", fill=(25, 25, 25), font=get_font(16))
    img_unreadable.save("data/test/marksheet_case8_unreadable.png")
    print("Generated data/test/marksheet_case8_unreadable.png")


if __name__ == "__main__":
    generate_test_files()
