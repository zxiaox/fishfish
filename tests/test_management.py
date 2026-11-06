import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('fishfish_catalog', Path('management/server.py'))
catalog = importlib.util.module_from_spec(spec)
spec.loader.exec_module(catalog)

class CatalogTests(unittest.TestCase):
    def test_persisted_ids_and_archiving(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'apps.json'
            path.write_text(json.dumps({'next_id': 1, 'apps': []}))
            data = {'name':'First', 'slug':'first', 'description':'Idea', 'status':'planned'}
            first = catalog.create_app(data, path)
            self.assertEqual(first['id'], 'A001')
            catalog.update_app('A001', {**data, 'status':'archived'}, path)
            second = catalog.create_app({**data, 'name':'Second', 'slug':'second'}, path)
            self.assertEqual(second['id'], 'A002')
            self.assertEqual(catalog.read_registry(path)['apps'][0]['status'], 'archived')
            with self.assertRaises(ValueError): catalog.create_app(data, path)
            with self.assertRaises(ValueError): catalog.update_app('A001', {**data, 'slug':'changed'}, path)
            with self.assertRaises(KeyError): catalog.update_app('A999', data, path)

    def test_existing_apps_have_stable_unique_ids(self):
        registry = catalog.read_registry()
        apps = registry['apps']
        expected = {'work-motivator':'A001', 'monty-hall':'A002', 'war3-battle-platform':'A003'}
        self.assertEqual({a['slug']:a['id'] for a in apps if a['slug'] in expected}, expected)
        self.assertEqual(len({a['id'] for a in apps}), len(apps))
        self.assertEqual(len({a['slug'] for a in apps}), len(apps))
        self.assertGreater(registry['next_id'], max(int(a['id'][1:]) for a in apps))
