from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from ai.src.config.settings import ARXConfig
from ai.src.data.loader import load_processed_csvs, split_work_ids


@dataclass
class SensorFrame:
    timestamp: str
    voltage: float
    current: float
    vacuum: float
    speed: float
    position: float | None = None
    temperature: float | None = None
    image_filename: str | None = None


class ISensorSource(ABC):

    @abstractmethod
    def session_id(self) -> str: ...

    @abstractmethod
    def source_name(self) -> str: ...

    @abstractmethod
    def total(self) -> int: ...

    @abstractmethod
    def read(self, index: int) -> SensorFrame: ...


class CsvReplaySource(ISensorSource):

    def __init__(self, csv_path: Path) -> None:
        if not csv_path.exists():
            raise FileNotFoundError(csv_path.name)
        self._path = csv_path
        self._df = pd.read_csv(csv_path, encoding="utf-8-sig")

    def session_id(self) -> str:
        return self._path.stem

    def source_name(self) -> str:
        return self._path.name

    def total(self) -> int:
        return len(self._df)

    def dataframe(self) -> pd.DataFrame:
        return self._df

    def read(self, index: int) -> SensorFrame:
        row = self._df.iloc[index]
        return SensorFrame(
            timestamp=str(row.get("datetime", "")),
            voltage=float(row.get("전압", 0) or 0),
            current=float(row.get("전류", 0) or 0),
            vacuum=float(row.get("진공도", 0) or 0),
            speed=float(row.get("하강속도", 0) or 0) if pd.notna(row.get("하강속도")) else 0.0,
            position=float(row["높이"]) if "높이" in self._df.columns and pd.notna(row.get("높이")) else None,
            temperature=None,
            image_filename=None,
        )


class CsvSourceCatalog:

    def __init__(self, data_dir: Path) -> None:
        self._data_dir = data_dir

    def list_files(self) -> list[str]:
        try:
            config = ARXConfig(data_dir=self._data_dir)
            data = load_processed_csvs(self._data_dir)
            split = split_work_ids(data, config)
            file_map = {p.stem: p.name for p in sorted(self._data_dir.glob("SA*_W*.csv"))}
            test_files = [file_map[w] for w in split["test_work_ids"] if w in file_map]
            if test_files:
                return test_files
        except Exception:
            pass
        return [p.name for p in sorted(self._data_dir.glob("SA*_W*.csv"))]

    def open(self, file_name: str | None) -> CsvReplaySource:
        if file_name:
            return CsvReplaySource(self._data_dir / file_name)
        files = sorted(self._data_dir.glob("SA*_W*.csv"))
        if not files:
            raise FileNotFoundError("No CSV files in processed directory")
        return CsvReplaySource(files[0])