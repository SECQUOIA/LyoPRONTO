#!/usr/bin/env python3
"""
Benchmark cleanup utility.

Automates maintenance tasks:
- Detect and archive duplicate/superseded artifacts
- Validate file naming conventions
- Generate artifact manifests
- Compress old result versions
- Enforce .gitignore patterns
"""

import json
import hashlib
from pathlib import Path
from typing import Dict, List, Tuple
from datetime import datetime
import sys

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))
from paths import get_results_dir, get_figures_dir, get_benchmarks_dir


class CleanupReport:
    """Track cleanup actions for reporting."""
    
    def __init__(self):
        self.duplicates_found = []
        self.naming_violations = []
        self.archived_files = []
        self.errors = []
    
    def add_duplicate(self, file1: Path, file2: Path, reason: str):
        self.duplicates_found.append((file1, file2, reason))
    
    def add_naming_violation(self, file: Path, reason: str):
        self.naming_violations.append((file, reason))
    
    def add_archived(self, file: Path, dest: Path):
        self.archived_files.append((file, dest))
    
    def add_error(self, file: Path, error: str):
        self.errors.append((file, error))
    
    def print_summary(self):
        print("\n" + "="*60)
        print("CLEANUP REPORT")
        print("="*60)
        
        if self.duplicates_found:
            print(f"\n🔍 Found {len(self.duplicates_found)} duplicate(s):")
            for f1, f2, reason in self.duplicates_found:
                print(f"  - {f1.name} ≈ {f2.name}")
                print(f"    Reason: {reason}")
        
        if self.naming_violations:
            print(f"\n⚠️  Found {len(self.naming_violations)} naming violation(s):")
            for file, reason in self.naming_violations:
                print(f"  - {file.name}: {reason}")
        
        if self.archived_files:
            print(f"\n📦 Archived {len(self.archived_files)} file(s):")
            for src, dest in self.archived_files:
                print(f"  - {src.name} → {dest}")
        
        if self.errors:
            print(f"\n❌ Encountered {len(self.errors)} error(s):")
            for file, error in self.errors:
                print(f"  - {file}: {error}")
        
        if not any([self.duplicates_found, self.naming_violations, 
                   self.archived_files, self.errors]):
            print("\n✅ No issues found - workspace is clean!")
        
        print("="*60 + "\n")


def compute_file_hash(filepath: Path, chunk_size: int = 8192) -> str:
    """Compute SHA256 hash of file contents."""
    sha256 = hashlib.sha256()
    with open(filepath, 'rb') as f:
        while chunk := f.read(chunk_size):
            sha256.update(chunk)
    return sha256.hexdigest()


def find_duplicate_images(figures_dir: Path, report: CleanupReport) -> List[Tuple[Path, Path]]:
    """
    Find duplicate image files (combined vs split heatmaps).
    
    Returns list of (keep, archive) tuples.
    """
    duplicates = []
    
    # Look for combined heatmaps when split versions exist
    if figures_dir.exists():
        for task_dir in figures_dir.iterdir():
            if not task_dir.is_dir():
                continue
            
            # Check objective diff heatmaps
            combined_obj = task_dir / "objective_diff_heatmap.png"
            fd_obj = task_dir / "objective_diff_heatmap_fd.png"
            colloc_obj = task_dir / "objective_diff_heatmap_colloc.png"
            
            if combined_obj.exists() and (fd_obj.exists() or colloc_obj.exists()):
                report.add_duplicate(combined_obj, fd_obj or colloc_obj, 
                                   "Combined heatmap superseded by split versions")
                duplicates.append(combined_obj)
            
            # Check speedup heatmaps
            combined_speed = task_dir / "speedup_heatmap.png"
            fd_speed = task_dir / "speedup_heatmap_fd.png"
            colloc_speed = task_dir / "speedup_heatmap_colloc.png"
            
            if combined_speed.exists() and (fd_speed.exists() or colloc_speed.exists()):
                report.add_duplicate(combined_speed, fd_speed or colloc_speed,
                                   "Combined heatmap superseded by split versions")
                duplicates.append(combined_speed)
            
            # Check old combined trajectory vs split trajectories
            combined_traj = task_dir / "nominal_trajectory.png"
            traj_tsh = task_dir / "nominal_trajectory_shelf_temperature.png"
            traj_pch = task_dir / "nominal_trajectory_chamber_pressure.png"
            traj_dried = task_dir / "nominal_trajectory_dried_fraction.png"
            
            if combined_traj.exists() and any([traj_tsh.exists(), traj_pch.exists(), traj_dried.exists()]):
                report.add_duplicate(combined_traj, traj_tsh or traj_pch or traj_dried,
                                   "Combined trajectory superseded by per-variable plots")
                duplicates.append(combined_traj)
    
    return duplicates


def validate_naming_conventions(figures_dir: Path, report: CleanupReport):
    """Check if figure files follow naming conventions."""
    
    # Expected patterns
    valid_prefixes = ['traj_', 'heatmap_obj_', 'heatmap_speed_', 'nominal_']
    valid_suffixes = ['_fd.png', '_colloc.png', '_combined.png', '.png']
    
    if not figures_dir.exists():
        return
    
    for task_dir in figures_dir.iterdir():
        if not task_dir.is_dir():
            continue
        
        for img_file in task_dir.glob("*.png"):
            name = img_file.name
            
            # Skip archive-bound files
            if "combined" not in name and not any(name.startswith(p) for p in valid_prefixes):
                # Check for inconsistent naming
                if "trajectory" in name and not name.startswith("traj_"):
                    report.add_naming_violation(img_file, 
                        "Should use 'traj_' prefix instead of 'nominal_trajectory_'")
                elif "heatmap" in name and not any(name.startswith(p) for p in ['heatmap_obj_', 'heatmap_speed_']):
                    report.add_naming_violation(img_file,
                        "Heatmap should use 'heatmap_obj_' or 'heatmap_speed_' prefix")


def generate_manifest(version: str) -> Dict:
    """Generate artifact manifest for a result version."""
    
    results_dir = get_results_dir(version)
    manifest = {
        "version": version,
        "generated_at": datetime.now().isoformat(),
        "artifacts": {
            "raw": [],
            "processed": [],
            "figures": {}
        }
    }
    
    # Catalog raw files
    raw_dir = results_dir / "raw"
    if raw_dir.exists():
        for file in raw_dir.glob("*"):
            if file.is_file():
                manifest["artifacts"]["raw"].append({
                    "name": file.name,
                    "size_bytes": file.stat().st_size,
                    "modified": datetime.fromtimestamp(file.stat().st_mtime).isoformat(),
                    "sha256": compute_file_hash(file) if file.suffix == ".jsonl" else None
                })
    
    # Catalog processed files
    processed_dir = results_dir / "processed"
    if processed_dir.exists():
        for file in processed_dir.glob("*"):
            if file.is_file():
                manifest["artifacts"]["processed"].append({
                    "name": file.name,
                    "size_bytes": file.stat().st_size,
                    "modified": datetime.fromtimestamp(file.stat().st_mtime).isoformat()
                })
    
    # Catalog figures by task
    figures_dir = results_dir / "figures"
    if figures_dir.exists():
        for task_dir in figures_dir.iterdir():
            if task_dir.is_dir():
                task_name = task_dir.name
                manifest["artifacts"]["figures"][task_name] = []
                for fig in task_dir.glob("*.png"):
                    manifest["artifacts"]["figures"][task_name].append({
                        "name": fig.name,
                        "size_bytes": fig.stat().st_size
                    })
    
    return manifest


def main():
    """Run cleanup checks and optionally apply fixes."""
    
    import argparse
    parser = argparse.ArgumentParser(description="Benchmark workspace cleanup utility")
    parser.add_argument("--version", default="test", help="Benchmark version to check")
    parser.add_argument("--archive-duplicates", action="store_true", 
                       help="Move duplicate files to archive/")
    parser.add_argument("--generate-manifest", action="store_true",
                       help="Generate artifact manifest JSON")
    parser.add_argument("--check-only", action="store_true",
                       help="Only report issues, don't fix")
    args = parser.parse_args()
    
    report = CleanupReport()
    
    print(f"🔍 Checking benchmark version: {args.version}")
    
    # Check for duplicates
    figures_dir = get_results_dir(args.version) / "figures"
    duplicates = find_duplicate_images(figures_dir, report)
    
    # Validate naming
    validate_naming_conventions(figures_dir, report)
    
    # Archive duplicates if requested
    if args.archive_duplicates and duplicates and not args.check_only:
        archive_dir = get_benchmarks_dir() / "archive" / "superseded_figures"
        archive_dir.mkdir(parents=True, exist_ok=True)
        
        for dup_file in duplicates:
            if dup_file.exists():
                dest = archive_dir / dup_file.name
                try:
                    dup_file.rename(dest)
                    report.add_archived(dup_file, dest)
                except Exception as e:
                    report.add_error(dup_file, str(e))
    
    # Generate manifest if requested
    if args.generate_manifest:
        manifest = generate_manifest(args.version)
        manifest_path = get_results_dir(args.version) / "manifest.json"
        with open(manifest_path, 'w') as f:
            json.dump(manifest, f, indent=2)
        print(f"\n📝 Manifest written to: {manifest_path}")
    
    # Print report
    report.print_summary()
    
    # Suggest next steps
    if duplicates and not args.archive_duplicates:
        print("💡 Tip: Run with --archive-duplicates to move superseded files to archive/")
    if not args.generate_manifest:
        print("💡 Tip: Run with --generate-manifest to create artifact inventory")


if __name__ == "__main__":
    main()
