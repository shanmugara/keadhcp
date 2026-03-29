import csv
import sys
def dedupe_csv(input_file, output_file):
    ipseen = set()
    seen = set()
    with open(input_file, 'r', newline='') as infile, open(output_file, 'w', newline='') as outfile:
        reader = csv.reader(infile)
        writer = csv.writer(outfile)
        for row in reader:
            print(f"Processing row: {row}")  # Debugging statement
            row_tuple = tuple(row)  # Convert list to tuple for hashing
            if row[0] in ipseen:
                print(f"Duplicate IP found: {row[0]}")  # Debugging statement
                continue
            else:
                ipseen.add(row[0])
            if row_tuple not in seen:
                seen.add(row_tuple)
                writer.writerow(row)    
if __name__ == "__main__":    
    if len(sys.argv) != 3:
        print("Usage: python dedupeleasecsv.py <input_csv> <output_csv>")
        sys.exit(1)
    input_csv = sys.argv[1]
    output_csv = sys.argv[2]
    dedupe_csv(input_csv, output_csv) 