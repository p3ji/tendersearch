---
description: Declare or edit a team of members
argument-hint: <team-id>
---

Create or update `teams/$1.yml` using `teams/_example.yml` as the schema.

Ask which members are on the team and who is prime. Verify every member has a
profile in `profiles/`.

**Never copy capabilities into the team file.** Teams list member IDs only;
service lines and regions are unioned from the member profiles at match time,
so a profile edit propagates automatically. A snapshot here would silently rot.

Verify it loads:

```bash
python -c "
from matching.profile import load_profiles, load_team
print(load_team('teams/$1.yml', load_profiles('profiles')).members)"
```
