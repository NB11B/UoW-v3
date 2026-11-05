import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from test_omarchy_service import OBS, TOKENS, POLICY

class ProcessTests(unittest.TestCase):
    def test_kill_restart_retry_and_malformed_lines(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "tokens.json").write_text(json.dumps(TOKENS))
            (root / "tokens.json").chmod(0o600)
            (root / "policy.json").write_text(json.dumps(POLICY))
            command = [sys.executable, "-m", "integrations.omarchy_uow.service", "--db", str(root / "state.db"), "--policy", str(root / "policy.json"), "--tokens", str(root / "tokens.json")]
            def start():
                env = {**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src") + os.pathsep + str(Path(__file__).resolve().parents[1])}
                return subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env)
            def send(p, req):
                p.stdin.write(json.dumps(req) + "\n"); p.stdin.flush()
                line = p.stdout.readline()
                self.assertTrue(line, "service terminated before responding")
                return json.loads(line)
            req = {"request_id": "p1", "token": "sensor-secret", "kind": "observation.ingest", "payload": OBS}
            p = start()
            try:
                self.assertEqual(send(p, {**req, "token": "\ud800"})["decision"], "DENIED")
                huge = {**OBS, "reading": {"value": 10**400, "unit": "percent"}}
                self.assertEqual(send(p, {**req, "request_id": "huge", "payload": huge})["reason"], "READING_RANGE")
                result = send(p, req)
                self.assertEqual(result["decision"], "COMMITTED")
                p.kill(); p.wait(timeout=5)  # no graceful shutdown after durable acknowledgement
            finally:
                if p.poll() is None: p.kill(); p.wait()
                p.stdin.close(); p.stdout.close(); p.stderr.close()
            # Kill a separate SQLite writer before commit; the journal must remain intact.
            writer = subprocess.Popen([sys.executable, "-c", "import sqlite3,sys,time; c=sqlite3.connect(sys.argv[1]); c.execute('BEGIN IMMEDIATE'); c.execute('DELETE FROM journal'); print('pending',flush=True); time.sleep(30)", str(root / "state.db")], stdout=subprocess.PIPE, text=True)
            try:
                self.assertEqual(writer.stdout.readline().strip(), "pending")
                writer.kill(); writer.wait(timeout=5)
            finally:
                if writer.poll() is None: writer.kill(); writer.wait()
                writer.stdout.close()
            p = start()
            try:
                self.assertEqual(send(p, req), result)
                summary = {"request_id": "p2", "token": "operator-secret", "kind": "observation.summarize", "payload": {"observation_id": "o1"}}
                response = send(p, summary)
                self.assertEqual(response["state"]["sequence"], 2)
                self.assertEqual(response["state"]["attributes"]["summary"]["value"], 23)
                p.stdin.close(); self.assertEqual(p.wait(timeout=5), 0)
            finally:
                if p.poll() is None: p.kill(); p.wait()
                p.stdout.close(); p.stderr.close()

if __name__ == "__main__": unittest.main(verbosity=2)
