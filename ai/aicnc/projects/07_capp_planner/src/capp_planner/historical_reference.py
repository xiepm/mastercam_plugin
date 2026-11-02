"""Read-only retrieval of historical planning references, never execution rules.

This evidence sidecar does not replace Manufacturing IR or knowledge_import's
candidate -> reviewed -> approved lifecycle. No automatic promotion is provided.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
from jsonschema import Draft202012Validator

SCHEMA = Path(__file__).resolve().parents[4] / 'schemas/historical_process_reference.schema.json'


def read_library(path: Path) -> dict:
    path = Path(path).resolve()
    data = json.loads(path.read_text(encoding='utf-8'))
    schema = json.loads(SCHEMA.read_text(encoding='utf-8'))
    Draft202012Validator(schema).validate(data)
    root = (path.parent / data['evidence_root']).resolve()
    by_path = {}
    for row in data['evidence']:
        target = (root / row['path']).resolve()
        if not target.is_relative_to(root):
            raise ValueError('evidence_path_outside_case')
        if row['path'] in by_path:
            raise ValueError('duplicate_evidence_path')
        digest = hashlib.sha256(target.read_bytes()).hexdigest()
        if digest != row['sha256']:
            raise ValueError('evidence_hash_mismatch: ' + row['path'])
        by_path[row['path']] = row
    seen = set()
    for item in data['templates']:
        if item['id'] in seen:
            raise ValueError('duplicate_template_id')
        seen.add(item['id'])
        if not set(item['evidence_paths']).issubset(by_path):
            raise ValueError('template_evidence_missing')
    frozen = by_path.get('02_initial_plan/独立工艺初稿.md')
    if frozen is None or frozen['sha256'] != data['frozen_initial_plan_sha256']:
        raise ValueError('frozen_initial_plan_binding_mismatch')
    return data


def retrieve(data: dict, terms: list[str], limit: int = 10) -> list[dict]:
    """Lexical AND-free ranking only; a hit is NOT an applicability decision."""
    if not 1 <= limit <= 100:
        raise ValueError('limit_must_be_1_to_100')
    terms = list(dict.fromkeys(t.strip().casefold() for t in terms if t.strip()))
    ranked = []
    for item in data['templates']:
        searchable = ' '.join([item['title'], *item['tags'], *item['conditions'],
                               item['historical_observation'], item['planning_advice']]).casefold()
        matched = [term for term in terms if term in searchable]
        if terms and not matched:
            continue
        ranked.append(dict(item, case_id=data['case_id'], matched_terms=matched,
                           retrieval_score=len(matched), applicability='must_compare_conditions'))
    return sorted(ranked, key=lambda row: (-row['retrieval_score'], row['id']))[:limit]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--library', required=True, type=Path)
    parser.add_argument('--terms', nargs='*', default=[])
    parser.add_argument('--limit', type=int, default=10)
    args = parser.parse_args()
    data = read_library(args.library)
    print(json.dumps(dict(case_id=data['case_id'], evidence_hashes_verified=True,
                         production_enabled=False,
                         results=retrieve(data,args.terms,args.limit)),ensure_ascii=False,indent=2))


if __name__ == '__main__':
    main()
