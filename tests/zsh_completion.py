#!/usr/bin/env python3
"""Exercise real Tab completion in an isolated interactive Zsh, without HTTP."""
import os
from pathlib import Path
import pty
import select
import shlex
import shutil
import signal
import subprocess
import tempfile
import time
import unittest

CLI = Path(os.environ.get('CLI', Path(__file__).resolve().parents[1] / 'target/debug/curlimp')).resolve()


class ZshCompletion(unittest.TestCase):
    def start_shell(self, autoload=False):
        temporary = tempfile.TemporaryDirectory(prefix='curlimp completion ')
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        script = subprocess.check_output([str(CLI), '--completions', 'zsh'])
        (root / '_curlimp').write_bytes(script)
        (root / 'curlimp').symlink_to(CLI)
        pid, self.fd = pty.fork()
        if pid == 0:
            os.environ.update(TERM='xterm', ZDOTDIR=str(root), HOME=str(root),
                              ALL_PROXY='http://127.0.0.1:1', NO_PROXY='')
            os.execv(shutil.which('zsh'), ['zsh', '-f', '-i'])

        def stop():
            os.close(self.fd)
            try:
                os.kill(pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            os.waitpid(pid, 0)
        self.addCleanup(stop)
        self.drain()
        quoted = shlex.quote(str(root))
        setup = f"path=({quoted} $path); zmodload zsh/complist; "
        if autoload:
            setup += f"fpath=({quoted} $fpath); "
        setup += "autoload -Uz compinit; compinit -D -i; "
        if not autoload:
            setup += f"source {quoted}/_curlimp; "
        setup += "zstyle ':completion:*:curlimp:*' menu yes select; "
        setup += "PROMPT='READY> '; RPROMPT=''; "
        setup += "capture_buffer() { print -r -- \"__BUFFER__${BUFFER}__END__\"; BUFFER=''; zle redisplay; }; "
        setup += "zle -N capture_buffer; bindkey '^X' capture_buffer; print '__SETUP_DONE__'\n"
        os.write(self.fd, setup.encode())
        self.until(b'__SETUP_DONE__\r\n')
        self.drain()

    def drain(self, timeout=0.15):
        data = b''
        while select.select([self.fd], [], [], timeout)[0]:
            try:
                data += os.read(self.fd, 65536)
            except OSError:
                break
            timeout = 0.03
        return data

    def until(self, marker):
        data = b''
        deadline = time.monotonic() + 8
        while marker not in data and time.monotonic() < deadline:
            data += self.drain()
        self.assertIn(marker, data, data.decode(errors='replace'))
        return data

    def buffer_after(self, keys, menu=False):
        os.write(self.fd, keys)
        screen = self.drain(timeout=1)
        if menu:
            os.write(self.fd, b'\r')
            screen += self.drain()
        os.write(self.fd, b'\x18')
        screen += self.until(b'__END__')
        text = screen.decode(errors='replace')
        self.assertIn('__BUFFER__', text)
        return text.split('__BUFFER__', 1)[1].split('__END__', 1)[0], text

    def test_unique_prefix_inserts_profile_for_sourced_completion(self):
        self.start_shell()
        buffer, _ = self.buffer_after(b'curlimp chrome15\t')
        self.assertEqual(buffer, 'curlimp chrome150 ')

    def test_menu_enter_keeps_command_in_editor(self):
        self.start_shell()
        buffer, screen = self.buffer_after(b'curlimp firefox14\t', menu=True)
        self.assertIn('firefox144', screen)
        self.assertIn('firefox147', screen)
        self.assertEqual(buffer, 'curlimp firefox144 ')

    def test_autoloaded_completion_uses_the_same_prefix_matching(self):
        self.start_shell(autoload=True)
        buffer, _ = self.buffer_after(b'curlimp -sSI chrome131_a\t')
        self.assertEqual(buffer, 'curlimp -sSI chrome131_android ')

    def test_empty_prefix_opens_the_profile_menu(self):
        self.start_shell()
        buffer, screen = self.buffer_after(b'curlimp \t', menu=True)
        self.assertIn('chrome150', screen)
        self.assertIn('tor145', screen)
        self.assertEqual(buffer, 'curlimp chrome100 ')

    def test_attached_profile_flag_completion(self):
        self.start_shell()
        buffer, _ = self.buffer_after(b'curlimp --impersonate=chrome15\t')
        self.assertEqual(buffer, 'curlimp --impersonate=chrome150 ')

    def test_flag_values_and_nonmatches_are_not_completed(self):
        self.start_shell()
        for keys, expected in [(b'curlimp -o chrome15\t', 'curlimp -o chrome15'),
                               (b'curlimp unknown-profile\t', 'curlimp unknown-profile')]:
            buffer, _ = self.buffer_after(keys)
            self.assertEqual(buffer, expected)


if __name__ == '__main__':
    unittest.main(verbosity=2)
