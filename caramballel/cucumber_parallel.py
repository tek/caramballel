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
import sys
import argparse
import copy
import datetime

instances = 0

class Cucumber(object):

    def __init__(self, base_port, args=None, use_xvfb_wrapper=True):
        self._base_port = base_port
        self._args = args or []
        self._use_xvfb_wrapper = use_xvfb_wrapper
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
        db_name = 'ulikeme_test_{0}'.format(offset)
        cmd = (['bundle', 'exec', 'cucumber', '--drb', '--port', str(port)] +
               self._args + [target])
        if self._use_xvfb_wrapper:
            cmd = ['xvfb-run', '--auto-servernum'] + cmd
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

def run_cucumber_parallel(_features=None, num_threads=None, cc_args=None,
                          base_port=0, use_xvfb_wrapper=True,
                          batch_features=False):
    cucumber = Cucumber(base_port, args=cc_args,
                        use_xvfb_wrapper=use_xvfb_wrapper)
    if not _features:
        _features = features('features')
    if not num_threads:
        num_threads = 5
    targets = (_features if batch_features
               else sum(map(scenarios, _features), []))
    threads = []
    for target in targets:
        while instances >= num_threads:
            time.sleep(1)
        threads.append(cucumber.thread(target))
    for thread in threads:
        thread.join()
    print_stats(cucumber)

def setup_argparse():
    parser = argparse.ArgumentParser()
    parser.add_argument('features', nargs='*', 'Features or scenarios to be'
                        ' processed')
    parser.add_argument('-n', '--num-threads', type=int, help='Number of'
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
    return parser.parse_args()

if __name__ == '__main__':
    args = setup_argparse()
    run_cucumber_parallel(_features=args.features,
                          num_threads=args.num_threads,
                          cc_args=args.cucumber_args.split(),
                          base_port=args.base_port,
                          use_xvfb_wrapper=not args.no_xvfb_wrapper,
                          batch_features=args.run_features)
