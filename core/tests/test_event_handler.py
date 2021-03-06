# Copyright 2016 Intel Corporation
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ------------------------------------------------------------------------------

from gossip.event_handler import EventHandler


class TestEventHandler(object):
    def __init__(self):
        pass

    def call1(self, ival):
        return ival < 5

    @staticmethod
    def call2(ival):
        return ival < 10

    def test_event_handler(self):
        ev = EventHandler("test")
        ev += self.call1
        ev += self.call2

        assert ev.fire(2)
        assert (not ev.fire(7))
        assert (not ev.fire(12))
