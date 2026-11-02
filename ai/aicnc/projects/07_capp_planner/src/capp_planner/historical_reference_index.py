"""Evidence-checked, curated cross-case retrieval; never an executable CAM plan."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from .historical_reference import SCHEMA, read_library


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate(data: dict, name: str) -> None:
    reference_schema = json.loads(SCHEMA.read_text('utf-8'))
    registry = Registry().with_resource(reference_schema['$id'], Resource.from_contents(reference_schema))
    Draft202012Validator(json.loads((SCHEMA.parent / name).read_text('utf-8')), registry=registry).validate(data)


def _inside(root: Path, relative: str) -> Path:
    target = (root / relative).resolve()
    if not target.is_relative_to(root):
        raise ValueError('catalog_path_outside_root')
    return target


def compile_index(catalog_path: Path, merge_plan_path: Path) -> dict:
    """All records must have exactly one human/agent-reviewed disposition.

    No clustering from name similarity, no parameter averaging, no deduplication
    of source records. Same STEP across multiple revisions counts as one geometry.
    """
    catalog_path, merge_plan_path = Path(catalog_path).resolve(), Path(merge_plan_path).resolve()
    catalog = json.loads(catalog_path.read_text('utf-8'))
    plan = json.loads(merge_plan_path.read_text('utf-8'))
    validate(catalog, 'local_reference_catalog.schema.json')
    validate(plan, 'historical_reference_merge.schema.json')
    root = catalog_path.parent
    records, cases = {}, set()
    for entry in catalog['cases']:
        if entry['case_id'] in cases:
            raise ValueError('duplicate_case_id')
        cases.add(entry['case_id'])
        path = _inside(root, entry['library'])
        _inside(root, entry['report'])
        if digest(path) != entry['library_sha256']:
            raise ValueError('catalog_library_hash_mismatch')
        lib = read_library(path)
        if lib['case_id'] != entry['case_id'] or len(lib['templates']) != entry['templates']:
            raise ValueError('catalog_library_identity_mismatch')
        for template in lib['templates']:
            if template['id'] in records:
                raise ValueError('duplicate_global_record_id')
            records[template['id']] = dict(case_id=lib['case_id'], part_name=lib['part_name'],
                source_step_sha256=lib['source_step_sha256'], source_mcam_sha256=lib['source_mcam_sha256'],
                library=entry['library'], library_sha256=entry['library_sha256'], record=template)
    used = set()

    def take(ids, category):
        variants = []
        for rid in ids:
            if rid in used:
                raise ValueError('record_has_multiple_dispositions: ' + rid)
            if rid not in records:
                raise ValueError('unknown_reference_record: ' + rid)
            item = records[rid]
            kind = item['record']['kind']
            if category == 'experience' and kind in ('historical_conflict', 'geometry_difference', 'missing_stage'):
                raise ValueError('unresolved_issue_cannot_be_experience: ' + rid)
            if category == 'conflict' and kind not in ('historical_conflict', 'geometry_difference'):
                raise ValueError('conflict_requires_conflict_kind: ' + rid)
            if category == 'gap' and kind not in ('input_gap', 'missing_stage'):
                raise ValueError('gap_requires_gap_kind: ' + rid)
            used.add(rid)
            variants.append(item)
        return variants

    families, family_ids = [], set()
    for family in plan['families']:
        if family['id'] in family_ids:
            raise ValueError('duplicate_family_id')
        family_ids.add(family['id'])
        variants = take(family['members'], 'experience')
        families.append(dict(id=family['id'], title=family['title'], summary=family['summary'],
            distinct_geometry_count=len({v['source_step_sha256'] for v in variants}),
            source_case_count=len({v['case_id'] for v in variants}), variants=variants,
            status='reference_candidate', production_enabled=False))
    conflicts, gaps = take(plan['conflicts'], 'conflict'), take(plan['gaps'], 'gap')
    if used != set(records):
        raise ValueError('undisposed_records: ' + ','.join(sorted(set(records)-used)))
    result = dict(schema_version='aicnc.historical-reference-index/0.1',
        production_enabled=False, applicability='must_compare_conditions',
        catalog_sha256=digest(catalog_path), merge_plan_sha256=digest(merge_plan_path),
        case_count=len(cases), record_count=len(records), families=families, conflicts=conflicts, gaps=gaps)
    validate(result, 'historical_reference_index.schema.json')
    return result


def retrieve_index(index: dict, terms: list[str], limit: int = 10) -> dict:
    if not 1 <= limit <= 100:
        raise ValueError('limit_must_be_1_to_100')
    terms = sorted({term.strip().casefold() for term in terms if term.strip()})

    def rank(rows):
        matches = []
        for row in rows:
            # Search advice/observations AND restrictions, returning complete variants.
            searchable = json.dumps(row, ensure_ascii=False).casefold()
            found = [term for term in terms if term in searchable]
            if not terms or found:
                matches.append(dict(row, matched_terms=found, retrieval_score=len(found)))
        return sorted(matches, key=lambda r: (-r['retrieval_score'], r.get('id', r.get('record', {}).get('id', ''))))[:limit]
    return dict(production_enabled=False, applicability='must_compare_conditions',
        families=rank(index['families']), conflicts=rank(index['conflicts']), gaps=rank(index['gaps']))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--catalog', type=Path, required=True)
    parser.add_argument('--merge-plan', type=Path, required=True)
    parser.add_argument('--output', type=Path, help='Optional reproducible index snapshot')
    parser.add_argument('--terms', nargs='*', default=[])
    parser.add_argument('--limit', type=int, default=10)
    args = parser.parse_args()
    index = compile_index(args.catalog, args.merge_plan)
    if args.output:
        target = args.output.resolve()
        root = args.catalog.resolve().parent
        if target in (args.catalog.resolve(), args.merge_plan.resolve()) or target.is_relative_to(root / 'cases'):
            raise ValueError('output_cannot_overwrite_sources')
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(retrieve_index(index, args.terms, args.limit), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
