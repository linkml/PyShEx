import argparse
import os
import sys
import textwrap
from argparse import ArgumentParser
from contextlib import redirect_stdout
from io import StringIO
from typing import Union, List, Optional, Callable

import pytest


class ArgParseExitException(Exception):
    ...


def _parser_exit(_: argparse.ArgumentParser, __=0, message: Optional[str] = None) -> None:
    raise ArgParseExitException(message)


ArgumentParser.exit = _parser_exit


class CLITestCase:
    testdir: str = None
    test_output_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), 'output'))
    test_input_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), 'input'))
    testprog: str = None

    @staticmethod
    def prog_ep(argv: List[str]) -> bool:
        return False

    @pytest.fixture(autouse=True, scope="class")
    def setup_testdir(self, tmp_path_factory):
        self.__class__.testdir_path = os.path.join(self.test_output_dir, self.testdir)
        os.makedirs(self.__class__.testdir_path, exist_ok=True)
        self.__class__.creation_messages = []
        yield
        if self.__class__.creation_messages:
            for msg in self.__class__.creation_messages:
                print(msg, file=sys.stderr)
            self.__class__.creation_messages = []
            pytest.fail("Tests failed because baseline files were being created")

    def do_test(self, args: Union[str, List[str]], testfile: Optional[str] = "",
                update_test_file: bool = False, error: type(Exception) = None,
                tox_wrap_fix: bool = False, failexpected: bool = False,
                text_filter: Callable[[str], str] = None) -> None:
        """Execute a cli test.

        Args:
            args: Argument string or list to command.
            testfile: Name of file to record output in. If absent, using directory mode.
            update_test_file: True means we need to update the test file.
            error: If present, we expect this error.
            tox_wrap_fix: tox seems to wrap redirected output at 60 columns. If true,
                try wrapping the test file before failing.
            failexpected: True means we're logging an error.
            text_filter: Edits to remove non-matchable items.
        """
        testfile_path = os.path.join(self.testdir_path, testfile)
        if text_filter is None:
            text_filter = lambda txt: "".join(txt.replace('\r\n', '\n').strip().split())

        outf = StringIO()
        arg_list = args.split() if isinstance(args, str) else args

        if error:
            with pytest.raises(error):
                self.prog_ep(arg_list)
            return

        with redirect_stdout(outf):
            try:
                success = not self.prog_ep(arg_list)
            except ArgParseExitException:
                success = False

        assert success or failexpected

        if not os.path.exists(testfile_path):
            with open(testfile_path, 'w') as f:
                f.write(outf.getvalue())
            self.__class__.creation_messages.append(f'{testfile_path} did not exist - updated')

        if testfile:
            with open(testfile_path) as f:
                new_txt = text_filter(outf.getvalue())
                old_txt = text_filter(f.read())
                if old_txt != new_txt and tox_wrap_fix:
                    old_txt = textwrap.fill(old_txt, 60)
                    new_txt = textwrap.fill(new_txt, 60)
                assert old_txt == new_txt
        else:
            print("Directory comparison needs to be added", file=sys.stderr)

    @staticmethod
    def clear_dir(folder: str) -> None:
        for filename in os.listdir(folder):
            file_path = os.path.join(folder, filename)
            try:
                if os.path.isfile(file_path):
                    os.unlink(file_path)
            except Exception as e:
                print(e)