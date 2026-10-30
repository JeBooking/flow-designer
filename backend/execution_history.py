"""有界历史投影缓存：变量按引擎修订号读取，客户端游标失效时返回完整快照。"""
from collections import OrderedDict
import copy
import json
import threading
import time
import uuid

from flowable_bridge import engine_request


class ExecutionHistory:
    def __init__(self, maximum=8, ttl=300, failure_reader=None):
        self.maximum, self.ttl = maximum, ttl
        self.entries = OrderedDict()
        self.lock = threading.RLock()
        self.failure_reader = failure_reader or engine_request

    def read(self, instance, cursor=None):
        with self.lock:
            now = time.monotonic()
            for key in list(self.entries):
                if now - self.entries[key]['accessed'] > self.ttl:
                    del self.entries[key]
            previous = self.entries.get(instance)
            versions = previous['versions'] if previous else {'variables': {}, 'activities': {}}
            result = engine_request('/diagnosis-api/instances/' + instance + '/history', json.dumps(versions).encode())
            removed_variables = list(versions['variables'].keys() - result['variableVersions'].keys())
            removed_activities = list(versions['activities'].keys() - result['activityVersions'].keys())
            variables = dict(previous['variables']) if previous else {}
            activities = dict(previous['activities']) if previous else {}
            for key in removed_variables:
                variables.pop(key, None)
            for key in removed_activities:
                activities.pop(key, None)
            variables.update((entry['id'], entry) for entry in result['variables']['data'])
            activities.update((entry['id'], entry) for entry in result['activities']['data'])
            changed = not previous or any((result['variables']['data'], result['activities']['data'],
                removed_variables, removed_activities, result['process'] != previous['process'],
                result['taskIds'] != previous['taskIds']))
            reviews = previous['pendingReviews'] if previous else []
            if changed:
                reviews = engine_request('/diagnosis-api/instances/' + instance + '/review/tasks')['tasks']
            failures = self.failure_reader('/process-api/management/deadletter-jobs?processInstanceId=' + instance)['data']
            old_failures = {entry['id']: entry for entry in previous['failures']} if previous else {}
            for failure in failures:
                old = old_failures.get(failure['id'])
                if failure.get('exceptionMessage'):
                    failure['traceback'] = old['traceback'] if old and old.get('exceptionMessage') == failure['exceptionMessage'] and 'traceback' in old else engine_request(
                        '/process-api/management/deadletter-jobs/' + failure['id'] + '/exception-stacktrace', as_text=True)
            changed = changed or not previous or failures != previous['failures']
            token = uuid.uuid4().hex if changed else previous['cursor']
            entry = {**result, 'variables': variables, 'activities': activities, 'pendingReviews': reviews,
                'failures': failures, 'cursor': token, 'accessed': now,
                'versions': {'variables': result['variableVersions'], 'activities': result['activityVersions']}}
            self.entries[instance] = entry
            self.entries.move_to_end(instance)
            while len(self.entries) > self.maximum:
                self.entries.popitem(last=False)
            reset = not previous or cursor != previous['cursor']
            response = {'process': result['process'], 'cursor': token, 'reset': reset,
                'nodes': result['nodes'], 'version': result['version'],
                'variables': {'data': list(variables.values()) if reset else result['variables']['data']},
                'activities': {'data': list(activities.values()) if reset else result['activities']['data']},
                'removedVariableIds': removed_variables, 'removedActivityIds': removed_activities,
                'changed': changed}
            if reset or changed:
                response.update(pendingReviews=reviews, failures=failures,
                    review=reviews[0] if reviews else {'pending': False})
            return copy.deepcopy(response)
