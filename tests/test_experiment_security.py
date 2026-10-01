import binascii
import contextlib
import io
import os
import signal
import struct
import time
import tracemalloc
import zipfile
import zlib

import pytest

from pipeline_toolkit.experiments.collect import _manifest
from pipeline_toolkit.experiments.contract import ExperimentError, MAX_BYTES
from pipeline_toolkit.experiments.github import BoundedProcess


def archive(data=b'{}', method=zipfile.ZIP_DEFLATED):
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', compression=method) as zipped:
        zipped.writestr('experiment-manifest.json', data)
    return bytearray(output.getvalue())


def collect(raw):
    class Boundary:
        def api(self, endpoint):
            return {'total_count': 1, 'artifacts': [{'id': 500, 'name': 'pipeline-experiment-manifest-1', 'expired': False, 'size_in_bytes': len(raw), 'workflow_run': {'id': 900, 'head_sha': 'a' * 40}}]}

        def raw(self, endpoint):
            return bytes(raw)

    return _manifest(Boundary(), {'baseline_ref': 'a' * 40}, 900, 1)[0]


@pytest.mark.parametrize('offset,value', [(18, 1), (22, 1), (14, 1), (6, 8)])
def test_local_zip_header_must_match_central_header(offset, value):
    raw = archive()
    struct.pack_into('<H' if offset == 6 else '<I', raw, offset, value)
    with pytest.raises(ExperimentError):
        collect(raw)


def test_matching_data_descriptor_flags_are_rejected():
    raw = archive()
    central = raw.index(b'PK\x01\x02')
    struct.pack_into('<H', raw, 6, 8)
    struct.pack_into('<H', raw, central + 8, 8)
    with pytest.raises(ExperimentError):
        collect(raw)


def test_central_filename_nul_cannot_hide_unexpected_name():
    raw = archive()
    central = raw.index(b'PK\x01\x02')
    end = raw.index(b'PK\x05\x06')
    raw[end:end] = b'\0evil'
    struct.pack_into('<H', raw, central + 28, len(b'experiment-manifest.json\0evil'))
    struct.pack_into('<I', raw, end + 5 + 12, end - central + 5)
    with pytest.raises(ExperimentError):
        collect(raw)


def test_forged_small_sizes_cannot_hide_large_deflate_expansion():
    # Generate a 64 MiB stream with only a 64 KiB working block. Do not
    # allocate the expanded adversarial payload even in the fixture.
    compressor = zlib.compressobj(wbits=-15)
    pieces = [compressor.compress(b'{}')]
    block = b' ' * 65536
    for _ in range(1024):
        pieces.append(compressor.compress(block))
    compressed = b''.join(pieces) + compressor.flush()
    name = b'experiment-manifest.json'
    crc = binascii.crc32(b'{}')
    local = struct.pack('<IHHHHHIIIHH', 0x04034b50, 20, 0, 8, 0, 0, crc, len(compressed), 2, len(name), 0) + name
    central = struct.pack('<I6H3I5H2I', 0x02014b50, 20, 20, 0, 8, 0, 0, crc, len(compressed), 2, len(name), 0, 0, 0, 0, 0, 0) + name
    end = struct.pack('<I4H2IH', 0x06054b50, 0, 0, 1, 1, len(central), len(local) + len(compressed), 0)
    tracemalloc.start()
    try:
        with pytest.raises(ExperimentError):
            collect(local + compressed + central + end)
        assert tracemalloc.get_traced_memory()[1] < 3 * MAX_BYTES
    finally:
        tracemalloc.stop()


@pytest.mark.parametrize('method', [zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED])
def test_bounded_zip_accepts_normal_manifest(method):
    assert collect(archive(method=method)) == {}


@pytest.mark.parametrize('name', ['experiment-manifest.json', 'unexpected.json'])
def test_duplicate_or_additional_zip_members_are_rejected(name):
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w') as zipped:
        zipped.writestr('experiment-manifest.json', '{}')
        with pytest.warns(UserWarning) if name == 'experiment-manifest.json' else contextlib.nullcontext():
            zipped.writestr(name, '{}')
    with pytest.raises(ExperimentError):
        collect(output.getvalue())


@pytest.mark.parametrize('handler', [signal.SIG_IGN, lambda *args: None])
def test_nondefault_child_reaping_is_rejected_before_launch(tmp_path, monkeypatch, handler):
    monkeypatch.setattr(signal, 'getsignal', lambda number: handler)
    launched = tmp_path / 'launched'
    executable = tmp_path / 'gh'
    executable.write_text('#!/bin/sh\ntouch "' + str(launched) + '"\n')
    executable.chmod(0o755)
    monkeypatch.setenv('PATH', str(tmp_path) + os.pathsep + os.environ['PATH'])
    with pytest.raises(ExperimentError, match='unsafe_process_reaping'):
        BoundedProcess().run(['gh'])
    assert not launched.exists()


@pytest.mark.skipif(not hasattr(os, 'fork'), reason='POSIX fork required')
def test_timeout_terminates_descendant_after_parent_exits(tmp_path, monkeypatch):
    executable = tmp_path / 'gh'
    heartbeat = tmp_path / 'heartbeat'
    pid_file = tmp_path / 'child.pid'
    executable.write_text('#!/usr/bin/env python3\nimport os,time,signal\nfrom pathlib import Path\npid=os.fork()\nif pid: os._exit(0)\nPath(' + repr(str(pid_file)) + ').write_text(str(os.getpid()))\nsignal.signal(signal.SIGTERM, signal.SIG_IGN)\nwhile True:\n Path(' + repr(str(heartbeat)) + ').write_text(str(time.monotonic()))\n time.sleep(.02)\n')
    executable.chmod(0o755)
    monkeypatch.setenv('PATH', str(tmp_path) + os.pathsep + os.environ['PATH'])
    started = time.monotonic()
    child = None
    try:
        with pytest.raises(ExperimentError, match='command_timeout'):
            BoundedProcess().run(['gh'], timeout=1.5)
        assert time.monotonic() - started < 3
        child = int(pid_file.read_text())
        last = heartbeat.read_text()
        time.sleep(.15)
        assert heartbeat.read_text() == last, 'descendant continues running after timeout'
    finally:
        if child is None and pid_file.exists():
            child = int(pid_file.read_text())
        if child is not None:
            try:
                os.kill(child, signal.SIGKILL)
            except ProcessLookupError:
                pass
