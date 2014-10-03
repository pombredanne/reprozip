#!/usr/bin/env python

# Copyright (C) 2014 New York University
# This file is part of ReproZip which is released under the Revised BSD License
# See file LICENSE for full license details.

import functools
import os
import re
from rpaths import Path, unicode
import subprocess
import sys
import yaml

from reprounzip.unpackers.common import join_root
from reprounzip.utils import iteritems


tests = Path(__file__).parent.absolute()


def in_temp_dir(f):
    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        tmp = Path.tempdir(prefix='reprozip_tests_')
        try:
            with tmp.in_dir():
                return f(*args, **kwargs)
        finally:
            tmp.rmtree(ignore_errors=True)
    return wrapper


def print_arg_list(f):
    """Decorator printing the sole argument (list of strings) first.
    """
    @functools.wraps(f)
    def wrapper(args):
        print(" ".join(a if isinstance(a, unicode)
                       else a.decode('utf-8', 'replace')
                       for a in args))
        return f(args)
    return wrapper


@print_arg_list
def call(args):
    r = subprocess.call(args)
    print("---> %d" % r)
    return r


@print_arg_list
def check_call(args):
    return subprocess.check_call(args)


@print_arg_list
def check_output(args):
    return subprocess.check_output(args)


def build(target, sources, args=[]):
    subprocess.check_call(['/usr/bin/env', 'CFLAGS=', 'cc', '-o', target] +
                          [(tests / s).path
                           for s in sources] +
                          args)


@in_temp_dir
def functional_tests(raise_warnings, interactive, run_vagrant, run_docker):
    python = [sys.executable]

    # Can't match on the SignalWarning category here because of a Python bug
    # http://bugs.python.org/issue22543
    python.extend(['-W', 'error:signal'])

    if 'COVER' in os.environ:
        python.extend(['-m'] + os.environ['COVER'].split(' '))

    reprozip_main = tests.parent / 'reprozip/reprozip/main.py'
    reprounzip_main = tests.parent / 'reprounzip/reprounzip/main.py'

    verbose = ['-v'] * 3
    rpz = python + [reprozip_main.absolute().path] + verbose
    rpuz = python + [reprounzip_main.absolute().path] + verbose

    # ########################################
    # 'simple' program: trace, pack, info, unpack
    #

    # Build
    build('simple', ['simple.c'])
    # Trace
    check_call(rpz + ['trace', '-d', 'rpz-simple',
                      './simple',
                      (tests / 'simple_input.txt').path,
                      'simple_output.txt'])
    orig_output_location = Path('simple_output.txt').absolute()
    assert orig_output_location.is_file()
    with orig_output_location.open(encoding='utf-8') as fp:
        assert fp.read().strip() == '42'
    orig_output_location.remove()
    # Read config
    with Path('rpz-simple/config.yml').open(encoding='utf-8') as fp:
        conf = yaml.safe_load(fp)
    other_files = set(Path(f).absolute() for f in conf['other_files'])
    expected = [Path('simple'), (tests / 'simple_input.txt')]
    assert other_files.issuperset([f.resolve() for f in expected])
    # Check input and output files
    input_files = conf['runs'][0]['input_files']
    assert (dict((k, Path(f).name)
                 for k, f in iteritems(input_files)) ==
            {'arg': b'simple_input.txt'})
    output_files = conf['runs'][0]['output_files']
    print(dict((k, Path(f).name) for k, f in iteritems(output_files)))
    # Here we don't test for dict equality, since we might have C coverage
    # files in the mix
    assert Path(output_files['arg']).name == b'simple_output.txt'
    # Pack
    check_call(rpz + ['pack', '-d', 'rpz-simple', 'simple.rpz'])
    Path('simple').remove()
    # Info
    check_call(rpuz + ['info', 'simple.rpz'])
    # Show files
    check_call(rpuz + ['showfiles', 'simple.rpz'])
    # Lists packages
    check_call(rpuz + ['installpkgs', '--summary', 'simple.rpz'])
    # Unpack directory
    check_call(rpuz + ['directory', 'setup', 'simple.rpz', 'simpledir'])
    # Run directory
    check_call(rpuz + ['directory', 'run', 'simpledir'])
    output_in_dir = join_root(Path('simpledir/root'), orig_output_location)
    with output_in_dir.open(encoding='utf-8') as fp:
        assert fp.read().strip() == '42'
    # Delete with wrong command (should fail)
    assert call(rpuz + ['chroot', 'destroy', 'simpledir']) != 0
    # Delete directory
    check_call(rpuz + ['directory', 'destroy', 'simpledir'])
    # Unpack chroot
    check_call(['sudo'] + rpuz + ['chroot', 'setup', '--bind-magic-dirs',
                                  'simple.rpz', 'simplechroot'])
    # Run chroot
    check_call(['sudo'] + rpuz + ['chroot', 'run', 'simplechroot'])
    output_in_chroot = join_root(Path('simplechroot/root'),
                                 orig_output_location)
    with output_in_chroot.open(encoding='utf-8') as fp:
        assert fp.read().strip() == '42'
    # Get output file
    check_call(['sudo'] + rpuz + ['chroot', 'download', 'simplechroot',
                                  'arg:output1.txt'])
    with Path('output1.txt').open(encoding='utf-8') as fp:
        assert fp.read().strip() == '42'
    # Replace input file
    check_call(['sudo'] + rpuz + ['chroot', 'upload', 'simplechroot',
                                  '%s:arg' % (tests / 'simple_input2.txt')])
    check_call(['sudo'] + rpuz + ['chroot', 'upload', 'simplechroot'])
    # Run again
    check_call(['sudo'] + rpuz + ['chroot', 'run', 'simplechroot'])
    output_in_chroot = join_root(Path('simplechroot/root'),
                                 orig_output_location)
    with output_in_chroot.open(encoding='utf-8') as fp:
        assert fp.read().strip() == '36'
    # Delete with wrong command (should fail)
    assert call(rpuz + ['directory', 'destroy', 'simplechroot']) != 0
    # Delete chroot
    check_call(['sudo'] + rpuz + ['chroot', 'destroy', 'simplechroot'])

    if not Path('/vagrant').exists():
        check_call(['sudo', 'sh', '-c', 'mkdir /vagrant; chmod 777 /vagrant'])

    # Unpack Vagrant-chroot
    check_call(rpuz + ['vagrant', 'setup/create', '--use-chroot', 'simple.rpz',
                       '/vagrant/simplevagrantchroot'])
    print("\nVagrant project set up in simplevagrantchroot")
    try:
        if run_vagrant:
            check_call(rpuz + ['vagrant', 'run', '--no-stdin',
                               '/vagrant/simplevagrantchroot'])
        elif interactive:
            print("Test and press enter")
            sys.stdin.readline()
    finally:
        Path('/vagrant/simplevagrantchroot').rmtree()
    # Unpack Vagrant without chroot
    check_call(rpuz + ['vagrant', 'setup/create', '--dont-use-chroot',
                       'simple.rpz',
                       '/vagrant/simplevagrant'])
    print("\nVagrant project set up in simplevagrant")
    try:
        if run_vagrant:
            check_call(rpuz + ['vagrant', 'run', '--no-stdin',
                               '/vagrant/simplevagrant'])
        elif interactive:
            print("Test and press enter")
            sys.stdin.readline()
    finally:
        Path('/vagrant/simplevagrant').rmtree()

    # Unpack Docker
    check_call(rpuz + ['docker', 'setup/create', 'simple.rpz', 'simpledocker'])
    print("\nDocker project set up in simpledocker")
    try:
        if run_docker:
            check_call(rpuz + ['docker', 'setup/build', 'simpledocker'])
            check_call(rpuz + ['docker', 'run', 'simpledocker'])
            # Get output file
            check_call(rpuz + ['docker', 'download', 'simpledocker',
                               'arg:doutput1.txt'])
            with Path('doutput1.txt').open(encoding='utf-8') as fp:
                assert fp.read().strip() == '42'
            # Replace input file
            check_call(rpuz + ['docker', 'upload', 'simpledocker',
                               '%s:arg' % (tests / 'simple_input2.txt')])
            check_call(rpuz + ['docker', 'upload', 'simpledocker'])
            check_call(rpuz + ['showfiles', 'simpledocker'])
            # Run again
            check_call(rpuz + ['docker', 'run', 'simpledocker'])
            # Get output file
            check_call(rpuz + ['docker', 'download', 'simpledocker',
                               'arg:doutput2.txt'])
            with Path('doutput2.txt').open(encoding='utf-8') as fp:
                assert fp.read().strip() == '36'
            # Destroy
            check_call(rpuz + ['docker', 'destroy', 'simpledocker'])
        elif interactive:
            print("Test and press enter")
            sys.stdin.readline()
    finally:
        if Path('simpledocker').exists():
            Path('simpledocker').rmtree()

    # ########################################
    # 'threads' program: testrun
    #

    # Build
    build('threads', ['threads.c'], ['-lpthread'])
    # Trace
    check_call(rpz + ['testrun', './threads'])

    # ########################################
    # 'segv' program: testrun
    #

    # Build
    build('segv', ['segv.c'])
    # Trace
    check_call(rpz + ['testrun', './segv'])

    # ########################################
    # 'exec_echo' program: trace, pack, run --cmdline
    #

    # Build
    build('exec_echo', ['exec_echo.c'])
    # Trace
    check_call(rpz + ['trace', './exec_echo', 'originalexecechooutput'])
    # Pack
    check_call(rpz + ['pack', 'exec_echo.rpz'])
    # Unpack chroot
    check_call(['sudo'] + rpuz + ['chroot', 'setup',
                                  'exec_echo.rpz', 'echochroot'])
    try:
        # Run original command-line
        output = check_output(['sudo'] + rpuz + ['chroot', 'run',
                                                 'echochroot'])
        assert output == b'originalexecechooutput\n'
        # Prints out command-line
        output = check_output(['sudo'] + rpuz + ['chroot', 'run',
                                                 'echochroot', '--cmdline'])
        assert any(b'./exec_echo originalexecechooutput' == s.strip()
                   for s in output.split(b'\n'))
        # Run with different command-line
        output = check_output(['sudo'] + rpuz + [
                'chroot', 'run', 'echochroot',
                '--cmdline', './exec_echo', 'changedexecechooutput'])
        assert output == b'changedexecechooutput\n'
    finally:
        check_call(['sudo'] + rpuz + ['chroot', 'destroy', 'echochroot'])

    # ########################################
    # 'exec_echo' program: testrun
    # This is built with -m32 so that we transition:
    #   python (x64) -> exec_echo (i386) -> echo (x64)
    #

    if sys.maxsize > 2 ** 32:
        # Build
        build('exec_echo32', ['exec_echo.c'], ['-m32'])
        # Trace
        check_call(rpz + ['testrun', './exec_echo32 42'])
    else:
        print("Can't try exec_echo transitions: not running on 64bits")

    # ########################################
    # Tracing non-existing program
    #

    check_call(rpz + ['testrun', './doesntexist'])

    # ########################################
    # 'connect' program: testrun
    #

    # Build
    build('connect', ['connect.c'])
    # Trace
    p = subprocess.Popen(rpz + ['testrun', './connect'],
                         stderr=subprocess.PIPE)
    stdout, stderr = p.communicate()
    stderr = stderr.split(b'\n')
    assert not any(b'program exited with non-zero code' in l for l in stderr)
    assert any(l for l in stderr
               if re.search(br'process connected to [0-9.]+:80', l))

    # ########################################
    # Copies back coverage report
    #

    coverage = Path('.coverage')
    if coverage.exists():
        coverage.copyfile(tests.parent / '.coverage.runpy')