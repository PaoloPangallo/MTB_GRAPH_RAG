import csv

sum_score = 0
count = 0
with open(r'c:\Users\paolo\Desktop\IspezioneDatasetTesi\mtb-graphrag\backend\evaluation\results\benchmark_summary.csv', 'r') as f:
    r = csv.DictReader(f)
    for row in r:
        sum_score += float(row['judge_score'])
        count += 1

print(f"Total cases: {count}")
print(f"Average judge score: {sum_score / count:.3f}")
