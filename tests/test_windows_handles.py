"""Detect leaked handles even on platforms which allow deleting open files."""
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import Mock, patch
from pcs_agent.trace import Store
from pcs_agent.instance import InstanceLock


class TraceHandleTests(unittest.TestCase):
    def test_every_trace_operation_closes_its_connection_without_gc(self):
        connect = sqlite3.connect
        connections = []
        def keep_reference(*args, **kwargs):
            db = connect(*args, **kwargs)
            connections.append(db)  # GC cannot conceal an unclosed connection.
            return db
        with tempfile.TemporaryDirectory() as folder:
            with patch('pcs_agent.trace.sqlite3.connect', side_effect=keep_reference):
                store = Store(folder)
                ident = store.create('Retain committed evidence')
                store.update(ident, status='running')
                store.event(ident, 'delta', {'text': 'partial'})
                store.get(ident)
                store.tasks()
                store.events(ident)
                store.export()
                store.recover()
            self.assertGreaterEqual(len(connections), 9)
            for db in connections:
                with self.assertRaises(sqlite3.ProgrammingError):
                    db.execute('SELECT 1')
            self.assertEqual(Store(folder).get(ident)['status'], 'interrupted')
            store.path.unlink()  # Windows must be able to delete it immediately.

    def test_failed_transaction_rolls_back_and_closes(self):
        with tempfile.TemporaryDirectory() as folder:
            store = Store(folder)
            with self.assertRaisesRegex(ValueError, 'abort'):
                with store.connect() as db:
                    db.execute("INSERT INTO tasks(id,prompt,status) VALUES('rolled-back','private','queued')")
                    raise ValueError('abort')
            with self.assertRaises(sqlite3.ProgrammingError):
                db.execute('SELECT 1')
            with self.assertRaises(KeyError):
                store.get('rolled-back')
            store.path.unlink()


class InstanceHandleTests(unittest.TestCase):
    def test_contended_lock_closes_descriptor_before_reading(self):
        with tempfile.TemporaryDirectory() as folder:
            stream = Mock()
            with patch('pathlib.Path.open', return_value=stream), patch('pcs_agent.instance._acquire_lock', side_effect=PermissionError('locked')):
                with self.assertRaisesRegex(RuntimeError, 'already running'):
                    InstanceLock(folder)
            stream.read.assert_not_called()
            stream.write.assert_not_called()
            stream.close.assert_called_once()

    def test_lock_acquired_before_content_access_and_read_error_closes(self):
        with tempfile.TemporaryDirectory() as folder:
            stream = Mock()
            acquired = []
            def read(size):
                self.assertTrue(acquired)
                raise PermissionError('read failed after acquisition')
            stream.read.side_effect = read
            with patch('pathlib.Path.open', return_value=stream), patch('pcs_agent.instance._acquire_lock', side_effect=lambda _: acquired.append(True)):
                with self.assertRaisesRegex(PermissionError, 'read failed'):
                    InstanceLock(folder)
            stream.close.assert_called_once()

    def test_unlock_error_still_closes_descriptor(self):
        lock = InstanceLock.__new__(InstanceLock)
        lock.stream = Mock(closed=False)
        with patch('pcs_agent.instance._release_lock', side_effect=OSError('unlock failed')):
            with self.assertRaisesRegex(OSError, 'unlock failed'):
                lock.close()
        lock.stream.close.assert_called_once()

    def test_real_lock_handles_empty_existing_file_and_reacquisition(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'strident-instance.lock'
            path.touch()
            first = InstanceLock(folder)
            try:
                for _ in range(3):
                    with self.assertRaisesRegex(RuntimeError, 'already running'):
                        InstanceLock(folder)
            finally:
                first.close()
            again = InstanceLock(folder)
            again.close()
            again.close()
            path.unlink()

if __name__ == '__main__':
    unittest.main()
