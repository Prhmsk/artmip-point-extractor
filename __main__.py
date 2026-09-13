from .catalogue import DATASETS

if __name__ == "__main__":
    print("Available datasets:")
    for dataset in DATASETS.values():
        print(f"- {dataset.label} ({dataset.supported_start}-{dataset.supported_end})")
