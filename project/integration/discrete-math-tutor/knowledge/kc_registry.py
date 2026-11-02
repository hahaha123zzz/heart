"""Read-only course KC registry; only reviewed, current mappings can measure."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path

REGISTRY_PATH = Path(__file__).parent / 'courses/experimental-psychology-3/kc_registry.json'


def _current_target(target_id):
    from knowledge.course_navigation import outline
    return next((unit for unit in outline() if unit['id'] == target_id), None)


def fingerprint(value):
    """Canonical digest of a complete JSON-compatible artifact."""
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()


def assessment_fingerprint(question, answer_key, rubric, mapping):
    return fingerprint({'question': question, 'answer_key': answer_key, 'rubric': rubric, 'mapping': mapping})


def registry_fingerprint(data):
    keys = ('schema', 'course_id', 'version', 'sources', 'knowledge_components', 'relations', 'target_mappings')
    return fingerprint({key: data.get(key) for key in keys})


def validate_registry(data):
    if data.get('schema') != 'kc-registry-v1' or not data.get('course_id') or not data.get('version'):
        raise ValueError('invalid registry identity')
    items = data.get('knowledge_components')
    if not isinstance(items, list):
        raise ValueError('knowledge_components must be a list')
    sources = {s['id']: s for s in data.get('sources', [])}
    if len(sources) != len(data.get('sources', [])):
        raise ValueError('duplicate source id')
    by_id = {}
    for item in items:
        kc_id = item.get('id')
        if not isinstance(kc_id, str) or not kc_id or kc_id in by_id:
            raise ValueError('missing or duplicate KC id')
        if item.get('status') not in ('candidate', 'reviewed', 'retired'):
            raise ValueError('invalid KC status')
        if not item.get('name') or not item.get('observable'):
            raise ValueError('KC name and observable behavior required')
        if item['status'] == 'reviewed' and not item.get('reviewer'):
            raise ValueError('reviewed KC needs reviewer')
        if item['status'] == 'reviewed' and not item.get('source_refs'):
            raise ValueError('reviewed KC needs source references')
        if not isinstance(item.get('aliases', []), list) or not all(isinstance(a, str) and a for a in item.get('aliases', [])):
            raise ValueError('invalid aliases')
        for ref in item.get('source_refs', []):
            source = sources.get(ref.get('source_id'))
            if not source or not ref.get('block_ids') or not set(ref['block_ids']).issubset(source.get('block_ids', [])):
                raise ValueError('invalid KC source reference')
        by_id[kc_id] = item
    edges = {kc_id: [] for kc_id in by_id}
    for edge in data.get('relations', []):
        source, target, kind = edge.get('from'), edge.get('to'), edge.get('type')
        if source not in by_id or target not in by_id or source == target:
            raise ValueError('invalid relation endpoint')
        if kind not in ('prerequisite', 'related_to', 'supersedes'):
            raise ValueError('invalid relation type')
        if kind == 'prerequisite':
            edges[source].append(target)
    visiting, done = set(), set()
    def visit(node):
        if node in visiting:
            raise ValueError('cyclic prerequisites')
        if node not in done:
            visiting.add(node)
            for dependency in edges[node]:
                visit(dependency)
            visiting.remove(node)
            done.add(node)
    for node in edges:
        visit(node)
    for mapping in data.get('target_mappings', []):
        if mapping.get('status') not in ('candidate', 'reviewed') or not mapping.get('target_id') or not mapping.get('target_version'):
            raise ValueError('invalid target mapping')
        if mapping['status'] == 'reviewed' and not mapping.get('reviewer'):
            raise ValueError('reviewed target mapping needs reviewer')
        if not mapping.get('kc_ids') or any(k not in by_id for k in mapping['kc_ids']):
            raise ValueError('invalid target mapping KC')
        if len(set(mapping['kc_ids'])) != len(mapping['kc_ids']):
            raise ValueError('duplicate target mapping KC')
        if mapping.get('source_id') not in sources:
            raise ValueError('target mapping needs source')
    seen = set()
    for record in data.get('assessment_mappings', []):
        mapping_id = record.get('id')
        if not mapping_id or mapping_id in seen or record.get('status') not in ('candidate', 'reviewed'):
            raise ValueError('invalid assessment mapping identity')
        if record['status'] == 'reviewed' and not record.get('reviewer'):
            raise ValueError('reviewed assessment mapping needs reviewer')
        mapping = record.get('mapping')
        if (not isinstance(mapping, dict) or not isinstance(mapping.get('criteria'), dict)
                or not mapping.get('target_id') or not mapping.get('target_version')):
            raise ValueError('assessment criteria mapping required')
        for criterion, entry in mapping['criteria'].items():
            if not criterion or not isinstance(entry, dict):
                raise ValueError('invalid assessment criterion')
            targeted, evaluated = entry.get('targeted_kcs'), entry.get('evaluated_kcs')
            if (not isinstance(targeted, list) or not isinstance(evaluated, list)
                    or any(k not in by_id for k in targeted + evaluated)
                    or not set(evaluated).issubset(targeted)
                    or len(set(targeted)) != len(targeted) or len(set(evaluated)) != len(evaluated)):
                raise ValueError('invalid assessment KC references')
        seen.add(mapping_id)
    return data


class KCRegistry:
    def __init__(self, data, source_root=None, target_resolver=None):
        self._data = validate_registry(deepcopy(data))
        self._items = {item['id']: item for item in self._data['knowledge_components']}
        self._assessments = {item['id']: item for item in self._data.get('assessment_mappings', [])}
        self._source_root = Path(source_root or REGISTRY_PATH.parent).resolve()
        self._target_resolver = target_resolver or _current_target

    @classmethod
    def load(cls, path=REGISTRY_PATH):
        path = Path(path)
        return cls(json.loads(path.read_text(encoding='utf-8')), path.parent)

    def audit_sources(self):
        result = {}
        for source in self._data.get('sources', []):
            valid = True
            for key, digest_key in (('document', 'document_sha256'), ('docx', 'docx_sha256')):
                try:
                    path = (self._source_root / source[key]).resolve()
                    valid = valid and path.is_relative_to(self._source_root) and path.is_file()
                    if valid:
                        valid = hashlib.sha256(path.read_bytes()).hexdigest() == source[digest_key]
                except (KeyError, OSError, ValueError):
                    valid = False
            if valid:
                try:
                    document = json.loads((self._source_root / source['document']).read_text(encoding='utf-8'))
                    blocks = {b['block_index'] for b in document['blocks']
                              if b.get('section_id') == source['section_id']}
                    valid = document['chapter_id'] == source['chapter_id'] and set(source['block_ids']).issubset(blocks)
                except (KeyError, TypeError, OSError, ValueError):
                    valid = False
            result[source['id']] = bool(valid)
        return result

    def find_alias(self, name):
        """Return all candidates; related concepts never become aliases."""
        return [deepcopy(item) for item in self._items.values()
                if name == item['name'] or name in item.get('aliases', [])]

    def target_kcs(self, target_id):
        """Resolve only a reviewed target and reviewed KCs at the exact version."""
        mappings = [m for m in self._data.get('target_mappings', [])
                    if m['status'] == 'reviewed' and m['target_id'] == target_id]
        if not mappings:
            return []
        try:
            target = self._target_resolver(target_id)
        except (OSError, ValueError, KeyError):
            return []
        if not isinstance(target, dict) or target.get('source_valid') is not True:
            return []
        valid_sources = self.audit_sources()
        ids = set()
        for mapping in mappings:
            if (valid_sources.get(mapping['source_id']) and mapping['target_id'] == target.get('id')
                    and mapping['target_version'] == target.get('version')):
                ids.update(k for k in mapping['kc_ids'] if self._items[k]['status'] == 'reviewed'
                           and all(valid_sources.get(ref['source_id']) for ref in self._items[k]['source_refs']))
        return sorted(ids)

    def path_objective_kcs(self, source_refs):
        """Match Q5 objective source identities to current, verified course targets."""
        if not isinstance(source_refs, list):
            return []
        found = set()
        for ref in source_refs:
            if not isinstance(ref, dict):
                continue
            if not any(m['status'] == 'reviewed' and m['target_id'] == ref.get('unit_id')
                       for m in self._data.get('target_mappings', [])):
                continue
            try:
                target = self._target_resolver(ref.get('unit_id'))
            except (OSError, ValueError, KeyError):
                continue
            if (isinstance(target, dict) and ref.get('unit_id') == target.get('id')
                    and ref.get('version') == target.get('version')):
                found.update(self.target_kcs(target['id']))
        return sorted(found)

    def evaluated_coverage(self, mapping_id, *, question, answer_key, rubric, verdicts):
        """Return individual criterion evidence; ambiguous multi-KC scores abstain."""
        record = self._assessments.get(mapping_id, {})
        if record.get('status') != 'reviewed' or not record.get('reviewer'):
            return []
        if not question or not answer_key or not rubric:
            return []
        mapping = record.get('mapping')
        try:
            current_fingerprint = assessment_fingerprint(question, answer_key, rubric, mapping)
        except (TypeError, ValueError):
            return []
        if not isinstance(mapping, dict) or record.get('fingerprint') != current_fingerprint:
            return []
        if (mapping.get('registry_version') != self._data['version']
                or mapping.get('registry_fingerprint') != registry_fingerprint(self._data)):
            return []
        try:
            target = self._target_resolver(mapping['target_id'])
        except (OSError, ValueError, KeyError):
            return []
        if not isinstance(target, dict) or target.get('version') != mapping['target_version']:
            return []
        target_kcs = self.target_kcs(mapping['target_id'])
        if not target_kcs:
            return []
        source_status = self.audit_sources()
        criteria = mapping.get('criteria')
        if not isinstance(criteria, dict) or not isinstance(verdicts, dict) or not isinstance(rubric, dict):
            return []
        result = []
        for criterion, entry in criteria.items():
            if not isinstance(entry, dict):
                continue
            targeted, evaluated = entry.get('targeted_kcs'), entry.get('evaluated_kcs')
            if not isinstance(targeted, list) or not isinstance(evaluated, list) or len(evaluated) != 1:
                continue
            kc_id = evaluated[0]
            if (kc_id not in targeted or kc_id not in target_kcs or kc_id not in self._items
                    or self._items[kc_id]['status'] != 'reviewed'
                    or not all(source_status.get(ref['source_id']) for ref in self._items[kc_id]['source_refs'])
                    or criterion not in rubric or criterion not in verdicts
                    or verdicts[criterion] not in ('met', 'not_met', 'partial', 'unclear')):
                continue
            result.append({'criterion_id': criterion, 'kc_id': kc_id, 'verdict': verdicts[criterion]})
        return result
