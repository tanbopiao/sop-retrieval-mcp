#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SOP 检索核心模块回归测试（unittest，纯标准库，可在干净环境运行）。

回归范围：每次改动后必须全绿的历史用例——
  1. 版本元数据抽取：版本号/生效日期/替代关系/文档族归并/冲突检测；
  2. 分块与检索：分节、滑窗分块、BM25 索引与版本加权排序；
  3. 登记库闭环：摄取→检索→删除→持久化重建；
  4. 防篡改指纹：文件内容 sha256 指纹，改动即重索引现形（回归核心）；
  5. 试用闸：许可签发与到期判定。

运行：python3 -m unittest discover -s tests -t .   （仓库根目录下）
不依赖 docx/pypdf/mcp——server 壳与二进制解析不在本回归范围。
"""
import importlib
import json
import os
import shutil
import sys
import tempfile
import unittest

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _REPO)

chunking = importlib.import_module("sop_mcp.chunking")
versions = importlib.import_module("sop_mcp.versions")
retrieval = importlib.import_module("sop_mcp.retrieval")
store_mod = importlib.import_module("sop_mcp.store")
trial = importlib.import_module("sop_mcp.trial")

SAMPLE = """SOP-WH-001: WAREHOUSE RECEIVING PROCEDURE
Version: 2.3
Effective Date: 2026-09-01
Supersedes: Version 2.2 dated 2026-03-15

1. PURPOSE
This procedure defines the receiving steps for inbound goods.

2. BEFORE UNLOADING
2.1 Verify the delivery vehicle seal number against the ASN.
2.2 Confirm the dock assignment on the dock schedule board.

3. INSPECTION
3.1 Check the temperature recorder for chilled goods.
3.2 Reject the delivery if the reading exceeds 8 degrees Celsius.
"""


def _write_sop(folder, name, text):
    path = os.path.join(folder, name)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return path


class 版本抽取回归(unittest.TestCase):
    def test_版本号抽取(self):
        self.assertEqual(versions.extract_version(SAMPLE, "x.txt"), "2.3")

    def test_生效日期抽取(self):
        self.assertEqual(versions.extract_effective_date(SAMPLE), "2026-09-01")

    def test_替代关系抽取(self):
        self.assertIn("2.2", versions.extract_supersedes(SAMPLE))

    def test_文档族归并(self):
        self.assertEqual(versions.doc_family("SOP_v2.1.docx"),
                         versions.doc_family("SOP_v3.0.docx"))

    def test_同族多版本记冲突(self):
        docs = {
            "a.txt": {"family": "sop", "version": "1.0"},
            "b.txt": {"family": "sop", "version": "2.0"},
        }
        self.assertEqual(len(versions.find_conflicts(docs)), 1)


class 分块与检索回归(unittest.TestCase):
    def test_分节(self):
        text = "Intro line\n\nPURPOSE:\nDo the thing.\n\nSAFETY:\nBe careful."
        sections = chunking.split_sections(text)
        titles = [t.rstrip(":") for t, _ in sections]
        self.assertIn("PURPOSE", titles)
        self.assertTrue(any("SAFETY" in t for t in titles))
        self.assertTrue(any("Do the thing." in s for _, s in sections))

    def test_滑窗分块有重叠(self):
        chunks = chunking.chunk_text(SAMPLE * 3, target=200, overlap=40)
        self.assertGreater(len(chunks), 1)

    def test_分词(self):
        toks = chunking.tokenize("Verify the seal number")
        self.assertIn("verify", toks)

    def test_bm25检索命中(self):
        idx = retrieval.BM25Index()
        chunks = chunking.build_chunks(
            _write_sop(tempfile.mkdtemp(), "SOP-WH-001_Receiving.txt", SAMPLE),
            "SOP-WH-001_Receiving.txt")[0]
        idx.add_chunks(chunks)
        hits = idx.search("seal number", top_k=3)
        self.assertTrue(hits and "seal" in hits[0]["text"].lower())

    def test_高版本加权靠前(self):
        idx = retrieval.BM25Index()
        for ver, text in (("1.0", SAMPLE), ("2.0", SAMPLE.replace("2.3", "2.0"))):
            for i, t in enumerate(chunking.chunk_text(text)):
                idx.add_chunks([{
                    "doc_id": "doc-" + ver,
                    "family": "doc",
                    "version_tuple": tuple(int(x) for x in ver.split(".")),
                    "section": "body",
                    "part": i,
                    "text": t,
                }])
        hits = idx.search("receiving steps", top_k=5, version_boost={"doc": (2, 0)})
        self.assertTrue(hits)
        self.assertEqual(hits[0]["doc_id"], "doc-2.0")


class 登记库闭环回归(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.data = os.path.join(self.tmp, "data")
        self.sops = os.path.join(self.tmp, "sops")
        os.makedirs(self.sops)
        _write_sop(self.sops, "SOP-WH-001_Receiving.txt", SAMPLE)
        _write_sop(self.sops, "SOP-WH-002_Putaway.txt",
                   SAMPLE.replace("RECEIVING", "PUTAWAY").replace("2.3", "1.1"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_摄取检索删除闭环(self):
        st = store_mod.Store(self.data)
        r = st.ingest_folder(self.sops)
        self.assertEqual(len(r["added"]), 2)
        self.assertTrue(st.search("seal number"))
        st.remove_document("SOP-WH-002_Putaway.txt")
        self.assertEqual(len(st.list_documents()), 1)

    def test_重复摄取按指纹跳过(self):
        st = store_mod.Store(self.data)
        st.ingest_folder(self.sops)
        r2 = st.ingest_folder(self.sops)
        self.assertEqual(r2["skipped_unchanged"], sorted(os.listdir(self.sops)))

    def test_防篡改指纹现形(self):
        """文件被改后 sha256 指纹变化，重摄取不再跳过而是重索引——篡改现形。"""
        st = store_mod.Store(self.data)
        st.ingest_folder(self.sops)
        target = os.path.join(self.sops, "SOP-WH-001_Receiving.txt")
        with open(target, "a", encoding="utf-8") as f:
            f.write("\n4. TAMPERED APPENDIX\n")
        r = st.ingest_folder(self.sops)
        self.assertIn("SOP-WH-001_Receiving.txt", r["added"])
        self.assertNotIn("SOP-WH-001_Receiving.txt", r["skipped_unchanged"])

    def test_持久化重建(self):
        st = store_mod.Store(self.data)
        st.ingest_folder(self.sops)
        st2 = store_mod.Store(self.data)  # 新实例从 manifest 重建
        self.assertEqual(len(st2.list_documents()), 2)
        self.assertTrue(st2.search("temperature recorder"))


class 试用闸回归(unittest.TestCase):
    def test_许可签发与在期判定(self):
        tmp = tempfile.mkdtemp()
        try:
            lic = trial.get_license(tmp)
            self.assertEqual(lic["type"], "free-evaluation")
            r = trial.check_trial(tmp)
            self.assertTrue(r["ok"])
            self.assertGreater(r["days_left"], 0)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_过期判定(self):
        tmp = tempfile.mkdtemp()
        try:
            lic = trial.get_license(tmp)
            lic["expires_at"] = "2020-01-01"
            with open(os.path.join(tmp, "license.json"), "w") as f:
                json.dump(lic, f)
            r = trial.check_trial(tmp)
            self.assertFalse(r["ok"])
            self.assertEqual(r["days_left"], 0)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
