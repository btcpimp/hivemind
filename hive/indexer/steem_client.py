import os
import time

from .http_client import HttpClient, RPCError

_shared_adapter = None
def get_adapter():
    global _shared_adapter
    if not _shared_adapter:
        steem = os.environ.get('STEEMD_URL')
        jussi = os.environ.get('JUSSI_URL')
        _shared_adapter = SteemClient(steem, jussi)
    return _shared_adapter


class SteemClient:

    def __init__(self, api_endpoint, jussi=None):
        self._jussi = bool(jussi)
        url = jussi or api_endpoint
        assert url, 'steem-API endpoint undefined'
        self._client = HttpClient(nodes=[url])

    def get_accounts(self, accounts):
        assert accounts, "no accounts passed to get_accounts"
        ret = self.__exec('get_accounts', accounts)
        assert ret, "get_accounts response was blank"
        assert len(accounts) == len(ret), "requested %d accounts got %d" % (len(accounts),len(ret))
        return ret

    def get_content_batch(self, tuples):
        posts = self.__exec_batch('get_content', tuples)

        # sanity-checking jussi responses
        for post in posts:
            assert post, "unexpected empty response: {}".format(post)
            assert 'author' in post, "invalid post: {}".format(post)

        return posts

    def get_block(self, num):
        return self.__exec('get_block', num)

    def _gdgp(self):
        tries = 0
        while True:
            try:
                ret = self.__exec('get_dynamic_global_properties')
                assert ret, "empty response for gdgp: {}".format(ret)
                assert 'time' in ret, "gdgp invalid resp: {}".format(ret)
            except (AssertionError, RPCError) as e:
                tries += 1
                print("gdgp failure, retry in {}s -- {}".format(tries, e))
                time.sleep(tries)
                continue
            break

        return ret

    def head_time(self):
        return self._gdgp()['time']

    def head_block(self):
        return self._gdgp()['head_block_number']

    def last_irreversible_block_num(self):
        return self._gdgp()['last_irreversible_block_num']

    def get_blocks_range(self, lbound, ubound): # [lbound, ubound)
        block_nums = range(lbound, ubound)
        required = set(block_nums)
        available = set()
        missing = required - available
        blocks = {}

        while missing:
            for block in self.__exec_batch('get_block', [[i] for i in missing]):
                if not 'block_id' in block:
                    print("WARNING: invalid block returned: {}".format(block))
                    continue
                num = int(block['block_id'][:8], base=16)
                if num in blocks:
                    print("WARNING: batch get_block returned dupe %d" % num)
                blocks[num] = block
            available = set(blocks.keys())
            missing = required - available
            if missing:
                print("WARNING: API missed blocks {}".format(missing))
                time.sleep(3)

        return [blocks[x] for x in block_nums]

    def __exec(self, method, *params):
        return self._client.exec(method, *params)

    def __exec_batch(self, method, params):
        """If jussi is enabled, use batch requests; otherwise, multi"""
        if self._jussi:
            tries = 0
            while True:
                try:
                    return list(self._client.exec_batch(method, params, batch_size=500))
                except (AssertionError, RPCError) as e:
                    tries += 1
                    print("batch {} failure, retry in {}s -- {}".format(method, tries, e))
                    time.sleep(tries)
                    continue

        return list(self._client.exec_multi_with_futures(
            method, params, max_workers=10))
