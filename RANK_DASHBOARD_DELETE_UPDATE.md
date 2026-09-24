# Rank / Dashboard / Deleted-account update

## Rank upgrade requirements
- Normal -> Iron: 500 coins + 5 successful referrals
- Iron -> Bronze: 1500 coins + 15 successful referrals
- Bronze -> Silver: 4000 coins + 30 successful referrals
- Silver -> Gold: 10000 coins + 60 successful referrals
- Gold -> Diamond: 25000 coins + 120 successful referrals

Upgrades remain sequential. Admin can still assign any rank directly.

## Deleted account behavior
Every user callback is revalidated against the current database record before it can execute. Old inline buttons from a deleted self account no longer perform account actions; they are replaced with the registration/reconnect screen.

Registration callbacks (QR, QR refresh, cancel login, send session) remain usable so the user can create a new self.

## Dashboard behavior
Every Home/Dashboard return reloads the current user record and renders:
- user-specific numeric ID
- self online/offline status
- current rank
- coins
- successful referrals
- XP
- command prefix

No universal numeric ID is hard-coded into the dashboard.
