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

from pipeline_toolkit.experiments.collect import _manifest, _manifest_bytes
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


def test_descriptor_flag_without_descriptor_is_rejected():
    raw = archive()
    central = raw.index(b'PK\x01\x02')
    struct.pack_into('<H', raw, 6, 8)
    struct.pack_into('<H', raw, central + 8, 8)
    with pytest.raises(ExperimentError):
        collect(raw)


def streaming_archive(data=b'{}', *, signed=True, method=zipfile.ZIP_DEFLATED):
    # A real non-seekable standard-library archiver produces the same bit-3,
    # zero-local-sizes, signed-descriptor layout as the Actions archiver stream.
    class Stream(io.BytesIO):
        def seek(self, *args):
            raise OSError('non-seekable upload stream')

    output = Stream()
    with zipfile.ZipFile(output, 'w', compression=method) as zipped:
        zipped.writestr('experiment-manifest.json', data)
    raw = bytearray(output.getvalue())
    if not signed:
        central = raw.index(b'PK\x01\x02')
        assert raw[central - 16:central - 12] == b'PK\x07\x08'
        del raw[central - 16:central - 12]
        end = raw.index(b'PK\x05\x06')
        struct.pack_into('<I', raw, end + 16, central - 4)
    return raw


@pytest.mark.parametrize('signed', [True, False])
@pytest.mark.parametrize('method', [zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED])
def test_standard_streaming_upload_zip_is_accepted(signed, method):
    raw = streaming_archive(signed=signed, method=method)
    assert struct.unpack_from('<H', raw, 6)[0] & 8
    assert raw[14:26] == b'\0' * 12
    assert collect(raw) == {}


def test_unsigned_crc_matching_descriptor_signature_is_unambiguous():
    # Literal 4-byte payload has CRC32 0x08074b50. Length, not scanning for
    # that signature, must determine the unsigned descriptor representation.
    payload = b'\xac\nz\xd5'
    assert _manifest_bytes(streaming_archive(payload, signed=False)) == payload


@pytest.mark.parametrize('signed', [True, False])
def test_streaming_zip_at_uncompressed_limit_is_accepted(signed):
    assert collect(streaming_archive(b'{}' + b' ' * (MAX_BYTES - 2), signed=signed)) == {}


@pytest.mark.parametrize('trailer', [b'junk', b'PK\x07\x08', b'\xab\xae\x05\x00'])
def test_extra_compressed_data_with_consistent_declared_sizes_is_rejected(trailer):
    raw = streaming_archive()
    central = raw.index(b'PK\x01\x02')
    end = raw.index(b'PK\x05\x06')
    descriptor = central - 16
    compressed = struct.unpack_from('<I', raw, central + 20)[0]
    raw[descriptor:descriptor] = trailer
    delta = len(trailer)
    struct.pack_into('<I', raw, central + delta + 20, compressed + delta)
    struct.pack_into('<I', raw, descriptor + delta + 8, compressed + delta)
    struct.pack_into('<I', raw, end + delta + 16, central + delta)
    with pytest.raises(ExperimentError):
        collect(raw)


@pytest.mark.parametrize('signed', [True, False])
@pytest.mark.parametrize('field', ['crc', 'compressed', 'size', 'local', 'central', 'trailing', 'overlap', 'concatenated', 'special'])
def test_streaming_zip_forgery_and_ambiguous_layout_are_rejected(signed, field):
    raw = streaming_archive(signed=signed)
    central = raw.index(b'PK\x01\x02')
    end = raw.index(b'PK\x05\x06')
    descriptor = central - (16 if signed else 12)
    values = descriptor + (4 if signed else 0)
    if field in ('crc', 'compressed', 'size'):
        struct.pack_into('<I', raw, values + {'crc': 0, 'compressed': 4, 'size': 8}[field], 1)
    elif field == 'local': struct.pack_into('<I', raw, 22, 1)
    elif field == 'central': struct.pack_into('<I', raw, central + 24, 1)
    elif field == 'special': struct.pack_into('<I', raw, central + 38, 0o020600 << 16)
    elif field == 'overlap': struct.pack_into('<I', raw, central + 20, 10000)
    elif field == 'concatenated': raw.extend(streaming_archive())
    elif field == 'trailing':
        raw[central:central] = b'junk'
        struct.pack_into('<I', raw, end + 4 + 16, central + 4)
    with pytest.raises(ExperimentError):
        collect(raw)


@pytest.mark.parametrize('field', ['crc', 'size'])
def test_descriptor_and_central_agreement_cannot_hide_actual_value_mismatch(field):
    raw = streaming_archive()
    central = raw.index(b'PK\x01\x02')
    descriptor_values = central - 12
    struct.pack_into('<I', raw, central + (16 if field == 'crc' else 24), 1)
    struct.pack_into('<I', raw, descriptor_values + (0 if field == 'crc' else 8), 1)
    with pytest.raises(ExperimentError):
        collect(raw)


@pytest.mark.parametrize('attributes', [0o020600 << 16, 0o060600 << 16, 0o010600 << 16, 0o040600 << 16, 0x10])
def test_nonregular_archive_member_is_rejected(attributes):
    raw = archive()
    central = raw.index(b'PK\x01\x02')
    struct.pack_into('<I', raw, central + 38, attributes)
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


@pytest.mark.parametrize('descriptor', [None, 'signed', 'unsigned'])
def test_forged_small_sizes_cannot_hide_large_deflate_expansion(descriptor):
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
    flags = 8 if descriptor else 0
    local_values = (0, 0, 0) if descriptor else (crc, len(compressed), 2)
    local = struct.pack('<IHHHHHIIIHH', 0x04034b50, 20, flags, 8, 0, 0, *local_values, len(name), 0) + name
    central = struct.pack('<I6H3I5H2I', 0x02014b50, 20, 20, flags, 8, 0, 0, crc, len(compressed), 2, len(name), 0, 0, 0, 0, 0, 0) + name
    descriptor_bytes = ((b'PK\x07\x08' if descriptor == 'signed' else b'') + struct.pack('<III', crc, len(compressed), 2)) if descriptor else b''
    end = struct.pack('<I4H2IH', 0x06054b50, 0, 0, 1, 1, len(central), len(local) + len(compressed) + len(descriptor_bytes), 0)
    tracemalloc.start()
    try:
        with pytest.raises(ExperimentError):
            collect(local + compressed + descriptor_bytes + central + end)
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
