import json
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from curve.cli import main
from curve.dataset import generate_synthetic_dataset, split_counts


class DatasetTests(unittest.TestCase):
    def test_split_counts_reserves_validation_and_test(self):
        splits = split_counts(5, val=1, test=1)

        self.assertEqual(splits.train, 3)
        self.assertEqual(splits.val, 1)
        self.assertEqual(splits.test, 1)

    def test_generate_synthetic_dataset_writes_index_and_splits(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            index = generate_synthetic_dataset(
                output_dir=temp_dir,
                count=4,
                seed=100,
                width=64,
                height=64,
                val_count=1,
                test_count=1,
            )

            self.assertEqual(index["splits"], {"train": 2, "val": 1, "test": 1})
            self.assertTrue((Path(temp_dir) / "dataset.json").exists())
            self.assertTrue((Path(temp_dir) / "train" / "sample-0000.png").exists())
            self.assertTrue((Path(temp_dir) / "val" / "sample-0002.json").exists())
            self.assertTrue((Path(temp_dir) / "test" / "sample-0003.json").exists())

    def test_generate_cli_writes_dataset_index(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with redirect_stdout(StringIO()):
                main(
                    [
                        "generate",
                        "-o",
                        temp_dir,
                        "--count",
                        "3",
                        "--seed",
                        "30",
                        "--width",
                        "64",
                        "--height",
                        "64",
                        "--val-count",
                        "1",
                        "--test-count",
                        "1",
                    ]
                )

            index = json.loads((Path(temp_dir) / "dataset.json").read_text())
            self.assertEqual(index["count"], 3)
            self.assertEqual(index["samples"][0]["split"], "train")


if __name__ == "__main__":
    unittest.main()

