#!/usr/bin/env python

__copyright__ = """ Copyright (c) 2012 Torsten Schmits

This program is free software; you can redistribute it and/or modify it
under the terms of the GNU General Public License as published by the
Free Software Foundation; either version 3 of the License, or (at your
option) any later version.

This program is distributed in the hope that it will be useful, but
WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program; if not, see <http://www.gnu.org/licenses/>.
"""

import os
import glob
import re
import time
import threading
import subprocess
import argparse
import datetime
import socket

instances = 0

class Cucumber(object):

    def __init__(self, base_port, args=None, use_xvfb_wrapper=True,
                 use_spork=True):
        self._base_port = base_port
        self._args = args or []
        self._use_xvfb_wrapper = use_xvfb_wrapper
        self._use_spork = use_spork
        self.output = []
        self._offsets_in_use = []
        self._start_time = datetime.datetime.now()

    def _get_offset(self):
        offset = 0
        while offset in self._offsets_in_use:
            offset += 1
        self._offsets_in_use.append(offset)
        return offset

    def target(self, target, instance):
        global instances
        offset = self._get_offset()
        port = self._base_port + offset
        cmd = ['bundle', 'exec', 'cucumber']
        if self._use_xvfb_wrapper:
            cmd = ['xvfb-run', '--auto-servernum'] + cmd
        if self._use_spork:
            cmd += ['--drb', '--port', str(port)]
        cmd += self._args + [target]
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE)
        out = proc.communicate()[0]
        print out
        self.output.extend(out.split('\n'))
        self._offsets_in_use.remove(offset)
        instances -= 1

    def thread(self, target):
        global instances
        thread = threading.Thread(target=self.target, args=(target, instances,))
        instances += 1
        print 'Starting cucumber child no. {0}: {1}'.format(instances, target)
        thread.start()
        return thread

    @property
    def statistics(self):
        stats = dict(scenario=[0, 0], step=[0, 0])
        scen_rex = re.compile('(\d+) (scenario|step)s?')
        passed_rex = re.compile('(\d+) passed')
        for i, line in enumerate(self.output):
            match = scen_rex.match(line)
            if match:
                match2 = passed_rex.search(line)
                stats[match.group(2)][0] += int(match.group(1))
                if match2:
                    stats[match.group(2)][1] += int(match2.group(1))
        stats['runtime'] = str(datetime.datetime.now() - self._start_time)
        return stats

def features(directory):
    return glob.glob(os.path.join(directory, '*.feature'))

def scenarios(feat_file):
    formatter = (feat_file + ':{0}').format
    is_scenario = lambda l: re.match('\s*Scenario', l)
    with open(feat_file) as f:
        return [formatter(i) for i, line in enumerate(f.readlines(), 1)
                if is_scenario(line)]

def print_stats(cucumber):
    stats = cucumber.statistics
    scen = stats['scenario']
    step = stats['step']
    print '{0} scenarios ({1} passed)'.format(scen[0], scen[1])
    print '{0} steps ({1} passed)'.format(step[0], step[1])
    print 'runtime: {0}'.format(stats['runtime'])

def run_cucumber_parallel(_features=None, num_procs=None, cc_args=None,
                          base_port=0, batch_features=False, **kw):
    cucumber = Cucumber(base_port, args=cc_args, **kw)
    if not _features:
        _features = features('features')
    if not num_procs:
        num_procs = 5
    targets = (_features if batch_features
               else sum(map(scenarios, _features), []))
    procs = []
    for target in targets:
        while instances >= num_procs:
            time.sleep(1)
        procs.append(cucumber.thread(target))
    for thread in procs:
        thread.join()
    print_stats(cucumber)

def wait_for_spork(num_procs, base_port=8990):
    ports = [base_port+i for i in xrange(num_procs)]
    while ports:
        for port in ports:
            try:
                s = socket.socket()
                s.connect(('localhost', port))
            except socket.error:
                pass
            else:
                ports.remove(port)
                s.close()
        time.sleep(1)

def run_spork(num_procs=None, mongo_name='test_', base_port=8990,
              _wait_for_spork=True):
    if not num_procs:
        num_procs = 5
    args = ['bundle', 'exec', 'spork', 'cucumber', '-p']
    for num in xrange(num_procs):
        subprocess.Popen(args + [str(base_port+num)])
    if _wait_for_spork:
        wait_for_spork(num_procs=num_procs, base_port=base_port)

def setup_argparse():
    parser = argparse.ArgumentParser()
    parser.add_argument('features', nargs='*', help='Features or scenarios to'
                        ' be processed')
    parser.add_argument('-n', '--num-procs', type=int, help='Number of'
                        'concurrent cucumber processes')
    parser.add_argument('--cucumber-args', default='', help='Arguments to'
                        ' pass to cucumber')
    parser.add_argument('--base-port', default=8990, type=int, help='Port of'
                        ' the first spork instance')
    parser.add_argument('--no-xvfb-wrapper', action='store_true',
                        help='Jenkins breaks X')
    parser.add_argument('--run-features', action='store_true', help='Run one'
                        ' feature per process rather than individual '
                        'scenarios')
    parser.add_argument('--no-spork', action='store_true', help='Don\'t use'
                        'spork')
    parser.add_argument('--run-spork', action='store_true', help='Launch the'
                        'spork services')
    parser.add_argument('--mongo-db', default='test_', help='prefix for mongo'
                        ' db name')
    parser.add_argument('--no-wait-for-spork', action='store_true',
                        help='Don\'t wait for all spork processes to be up and'
                        'running')
    return parser.parse_args()

if __name__ == '__main__':
    args = setup_argparse()
    if args.run_spork:
        run_spork(num_procs=args.num_procs, mongo_name=args.mongo_db,
                  _wait_for_spork=not args.no_wait_for_spork)
    else:
        run_cucumber_parallel(_features=args.features,
                              num_procs=args.num_procs,
                              cc_args=args.cucumber_args.split(),
                              base_port=args.base_port,
                              use_xvfb_wrapper=not args.no_xvfb_wrapper,
                              batch_features=args.run_features,
                              use_spork=not args.no_spork)
