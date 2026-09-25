"""End-to-end API tests for the annotation coverage blind-spot workbench.

Run with: python3 test_coverage_api.py  (or via pytest).
"""
import os
import shutil
import tempfile

os.environ.setdefault("STATIC_DIR", "/nonexistent")
_TMP = tempfile.mkdtemp(prefix="coverage-api-")
os.environ["DATA_DIR"] = _TMP

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

DOC = {
    "segments": [
        # 访谈者: touching pieces [0,5)+[5,10) and the contained [2,4)
        # merge into one speech interval [0,10)
        {"id": "s1", "start": 0, "end": 5,
         "speaker": "访谈者", "text": "开场"},
        {"id": "s2", "start": 5, "end": 10,
         "speaker": "访谈者", "text": "提问"},
        {"id": "s3", "start": 2, "end": 4,
         "speaker": "访谈者", "text": "插一句"},
        # 受访者 overlaps 访谈者 on [8,10): counted separately per speaker
        {"id": "s4", "start": 8, "end": 18,
         "speaker": "受访者", "text": "回答"},
        # ignored: blank speaker, zero-length and non-numeric bounds
        {"id": "s5", "start": 20, "end": 22,
         "speaker": "   ", "text": "无说话人"},
        {"id": "s6", "start": 23, "end": 23,
         "speaker": "访谈者", "text": "零长度"},
        {"id": "s7", "start": "x", "end": 30,
         "speaker": "访谈者", "text": "非法时间"},
    ],
    "annotations": [
        # same-speaker overlapping annotations merge: [0,6)+[4,8) -> [0,8)
        {"id": "a1", "start": 0, "end": 6,
         "speaker": "访谈者", "topic": "甲"},
        {"id": "a2", "start": 4, "end": 8,
         "speaker": "访谈者", "topic": "乙"},
        # extends beyond the speech interval: only [9,10) counts
        {"id": "a3", "start": 9, "end": 12,
         "speaker": "访谈者", "topic": "丙"},
        # different speaker: does NOT cover 访谈者's speech
        {"id": "a4", "start": 0, "end": 3,
         "speaker": "受访者", "topic": "丁"},
        # empty speaker: covers nothing
        {"id": "a5", "start": 0, "end": 3,
         "speaker": "", "topic": "戊"},
        # covers the head of 受访者's speech
        {"id": "a6", "start": 8, "end": 10,
         "speaker": "受访者", "topic": "己"},
        # speaker without any speech: not listed, covers nothing
        {"id": "a7", "start": 0, "end": 2,
         "speaker": "路人", "topic": "庚"},
    ],
}


def run():
    with TestClient(app) as c:
        assert c.get("/api/health").json()["status"] == "ok"
        p = c.post("/api/projects", json={"name": "覆盖盲区访谈"}).json()
        pid = p["id"]
        c.put(f"/api/projects/{pid}",
              json={"name": "覆盖盲区访谈", "document": DOC})

        r = c.get(f"/api/projects/{pid}/coverage")
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["projectId"] == pid
        assert data["projectName"] == "覆盖盲区访谈"
        assert [s["speaker"] for s in data["speakers"]] == ["访谈者", "受访者"]

        iv = data["speakers"][0]
        assert iv["segmentCount"] == 3
        assert iv["annotationCount"] == 3
        assert iv["speechSeconds"] == 10.0
        assert iv["speechIntervals"] == [{"start": 0.0, "end": 10.0}]
        # overlapping same-name annotations merged, out-of-speech tail clipped
        assert iv["coveredIntervals"] == [
            {"start": 0.0, "end": 8.0}, {"start": 9.0, "end": 10.0}]
        assert iv["coveredSeconds"] == 9.0
        assert iv["uncoveredSeconds"] == 1.0
        assert iv["coverageRate"] == 0.9
        assert iv["blindSpots"] == [
            {"start": 8.0, "end": 9.0, "duration": 1.0}]

        su = data["speakers"][1]
        assert su["segmentCount"] == 1
        assert su["annotationCount"] == 2  # a4 (fully outside) + a6
        assert su["speechSeconds"] == 10.0
        assert su["coveredIntervals"] == [{"start": 8.0, "end": 10.0}]
        assert su["coveredSeconds"] == 2.0
        assert su["uncoveredSeconds"] == 8.0
        assert su["coverageRate"] == 0.2
        assert su["blindSpots"] == [
            {"start": 10.0, "end": 18.0, "duration": 8.0}]

        s = data["summary"]
        assert s["speakerCount"] == 2
        assert s["speechSeconds"] == 20.0
        assert s["coveredSeconds"] == 11.0
        assert s["uncoveredSeconds"] == 9.0
        assert s["coverageRate"] == 0.55
        assert s["blindSpotCount"] == 2

        # the report is read-only: the saved document is unchanged
        again = c.get(f"/api/projects/{pid}").json()["document"]
        assert again == DOC

        # speaker filter: exact name, summary recomputed over the selection
        r2 = c.get(f"/api/projects/{pid}/coverage", params={"speaker": "访谈者"})
        assert r2.status_code == 200
        d2 = r2.json()
        assert [sp["speaker"] for sp in d2["speakers"]] == ["访谈者"]
        assert d2["summary"]["speakerCount"] == 1
        assert d2["summary"]["speechSeconds"] == 10.0
        assert d2["summary"]["coveredSeconds"] == 9.0
        assert d2["summary"]["coverageRate"] == 0.9
        assert d2["summary"]["blindSpotCount"] == 1

        # unknown speaker name -> empty report, not an error
        r3 = c.get(f"/api/projects/{pid}/coverage", params={"speaker": "不存在"})
        assert r3.status_code == 200
        d3 = r3.json()
        assert d3["speakers"] == []
        assert d3["summary"]["speakerCount"] == 0
        assert d3["summary"]["speechSeconds"] == 0.0
        assert d3["summary"]["coverageRate"] == 0.0
        assert d3["summary"]["blindSpotCount"] == 0

        # empty project -> empty report
        p2 = c.post("/api/projects", json={"name": "空项目"}).json()
        r4 = c.get(f"/api/projects/{p2['id']}/coverage")
        assert r4.status_code == 200
        assert r4.json()["speakers"] == []
        assert r4.json()["summary"]["speechSeconds"] == 0.0

        # unknown project -> 404
        r5 = c.get("/api/projects/proj-nope/coverage")
        assert r5.status_code == 404
        assert r5.json()["detail"] == "项目不存在"

    shutil.rmtree(_TMP, ignore_errors=True)
    print("coverage API tests OK")


if __name__ == "__main__":
    run()
