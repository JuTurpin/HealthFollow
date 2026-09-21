#!/usr/bin/env python3
"""
Remet le projet à zéro avant un import complet.

Usage :
  .venv/bin/python reset.py            # supprime les données générées, conserve journal.json
  .venv/bin/python reset.py --all      # supprime tout, y compris journal.json
  .venv/bin/python reset.py --yes      # pas de confirmation
  .venv/bin/python reset.py --all --yes
"""
import argparse
import os
import shutil
import sys

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))

GENERATED = [
    os.path.join(PROJECT_ROOT, "sortie-sante", "workouts.csv"),
    os.path.join(PROJECT_ROOT, "sortie-sante", "daily.csv"),
    os.path.join(PROJECT_ROOT, "sortie-sante", "weekly.csv"),
    os.path.join(PROJECT_ROOT, "sortie-sante", "digest.md"),
    os.path.join(PROJECT_ROOT, "sortie-sante", "quality_report.json"),
    os.path.join(PROJECT_ROOT, "data", "last_export.zip"),
    os.path.join(PROJECT_ROOT, "data", ".details_progress"),
]
GENERATED_DIRS = [
    os.path.join(PROJECT_ROOT, "details"),
]
JOURNAL = os.path.join(PROJECT_ROOT, "journal.json")


def confirm(msg: str) -> bool:
    ans = input(f"{msg} [o/N] ").strip().lower()
    return ans in ("o", "oui", "y", "yes")


def main():
    ap = argparse.ArgumentParser(description="Remet les données du projet à zéro.")
    ap.add_argument("--all",  action="store_true", help="supprime aussi journal.json")
    ap.add_argument("--yes",  action="store_true", help="pas de confirmation")
    args = ap.parse_args()

    targets = []
    for path in GENERATED:
        if os.path.exists(path):
            targets.append(("fichier", path))
    for d in GENERATED_DIRS:
        if os.path.isdir(d):
            targets.append(("dossier", d))
    if args.all and os.path.exists(JOURNAL):
        targets.append(("fichier", JOURNAL))

    if not targets:
        print("Rien à supprimer.")
        return

    print("Éléments à supprimer :")
    for kind, path in targets:
        rel = os.path.relpath(path, PROJECT_ROOT)
        print(f"  {kind:8s}  {rel}")

    if not args.yes and not confirm("\nConfirmer la suppression ?"):
        print("Annulé.")
        sys.exit(0)

    for kind, path in targets:
        if kind == "dossier":
            shutil.rmtree(path)
        else:
            os.remove(path)
        print(f"  ✓  {os.path.relpath(path, PROJECT_ROOT)}")

    print("\nReset terminé. Lance l'app puis importe ton export complet.")


if __name__ == "__main__":
    main()
