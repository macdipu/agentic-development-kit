"""One spelling per human in approval and budget records.

`--by` is an operator assertion, not authentication (see the capability matrix).
It still has to be *consistent*: the same person recorded as `macdipu`,
`macdipu <me@x>`, and `user` cannot be audited. The git-configured identity of
the machine recording the decision is the canonical spelling; a different
reviewer's name is kept verbatim.
"""
from .handoff import git_user

# Placeholders an agent tends to type for "the person in this chat".
_ALIASES = {'user', 'me', 'operator', 'human', 'the user'}


def approver(repo, by=None) -> str:
    own = git_user(repo)
    if not by or not by.strip():
        if own == '(unknown)':
            raise ValueError('No --by given and git user.name/user.email are unset; configure git or pass --by')
        return own
    given = by.strip()
    if own != '(unknown)':
        name, _, email = own.partition(' <')
        spellings = {own.lower(), name.lower(), email.rstrip('>').lower()}
        if given.lower() in spellings | _ALIASES:
            return own
    elif given.lower() in _ALIASES:
        raise ValueError(f'--by {given!r} names no one; configure git user.name/user.email or pass a real name')
    return given
