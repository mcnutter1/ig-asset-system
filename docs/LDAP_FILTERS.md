# LDAP User Import Filters

This document provides examples of LDAP filters for importing users from Active Directory.

## Understanding LDAP Filters

LDAP filters use a prefix notation syntax with logical operators:
- `&` = AND (all conditions must match)
- `|` = OR (any condition can match)
- `!` = NOT (condition must not match)

Filters are wrapped in parentheses, and complex filters nest conditions.

## Default Filter

If no filter is provided, the system uses:
```ldap
(&(objectClass=user)(objectCategory=person)(!userAccountControl:1.2.840.113556.1.4.803:=2))
```

This finds:
- Objects that are `user` class
- In the `person` category
- NOT disabled (userAccountControl bit 2 is not set)

## Example Filters

### 1. All Active Users (Default)
```ldap
(&(objectClass=user)(objectCategory=person)(!userAccountControl:1.2.840.113556.1.4.803:=2))
```

**What it does:**
- Finds all user accounts
- Excludes disabled accounts
- Excludes computer accounts

---

### 2. Users in Specific OU
```ldap
(&(objectClass=user)(objectCategory=person)(!userAccountControl:1.2.840.113556.1.4.803:=2))
```

**Note:** You control the OU by setting the **Base DN** in LDAP settings, not the filter.

**Example Base DN:**
```
OU=IT Department,OU=Users,DC=corp,DC=example,DC=com
```

---

### 3. Users in Specific OU and Subfolders
Same as above - the `ldap_search()` function searches recursively by default.

To search ONLY the specified OU (not subfolders), use `ldap_list()` instead (requires code change).

---

### 4. Users with Email Addresses Only
```ldap
(&(objectClass=user)(objectCategory=person)(!userAccountControl:1.2.840.113556.1.4.803:=2)(mail=*))
```

**What it does:**
- Same as default
- PLUS requires the `mail` attribute to be present

---

### 5. Users in a Specific Group
```ldap
(&(objectClass=user)(objectCategory=person)(!userAccountControl:1.2.840.113556.1.4.803:=2)(memberOf=CN=IT-Staff,OU=Groups,DC=corp,DC=example,DC=com))
```

**What it does:**
- Finds active users
- Who are members of the "IT-Staff" group

**Important:** This only checks direct group membership, not nested groups.

---

### 6. Users in Multiple Specific Groups (OR)
```ldap
(&(objectClass=user)(objectCategory=person)(!userAccountControl:1.2.840.113556.1.4.803:=2)(|(memberOf=CN=IT-Staff,OU=Groups,DC=corp,DC=example,DC=com)(memberOf=CN=Admins,OU=Groups,DC=corp,DC=example,DC=com)))
```

**What it does:**
- Finds active users
- In either "IT-Staff" OR "Admins" group

---

### 7. Users Matching Name Pattern
```ldap
(&(objectClass=user)(objectCategory=person)(!userAccountControl:1.2.840.113556.1.4.803:=2)(|(cn=John*)(cn=Jane*)))
```

**What it does:**
- Finds active users
- Whose Common Name (cn) starts with "John" or "Jane"

---

### 8. Users with Specific Department
```ldap
(&(objectClass=user)(objectCategory=person)(!userAccountControl:1.2.840.113556.1.4.803:=2)(department=IT))
```

**What it does:**
- Finds active users
- In the "IT" department (based on the department attribute)

---

### 9. Users Created After Specific Date
```ldap
(&(objectClass=user)(objectCategory=person)(!userAccountControl:1.2.840.113556.1.4.803:=2)(whenCreated>=20240101000000.0Z))
```

**What it does:**
- Finds active users
- Created on or after January 1, 2024

**Date format:** `YYYYMMDDhhmmss.0Z` (UTC timezone)

---

### 10. Service Accounts Only
```ldap
(&(objectClass=user)(objectCategory=person)(description=*Service Account*))
```

**What it does:**
- Finds all user objects
- With "Service Account" in the description
- Includes disabled accounts (useful for service accounts)

---

### 11. Exclude Service Accounts
```ldap
(&(objectClass=user)(objectCategory=person)(!userAccountControl:1.2.840.113556.1.4.803:=2)(!description=*Service Account*)(!description=*System Account*))
```

**What it does:**
- Finds active users
- Excludes accounts with "Service Account" or "System Account" in description

---

### 12. Complex Example: IT Department, Active, with Email
```ldap
(&(objectClass=user)(objectCategory=person)(!userAccountControl:1.2.840.113556.1.4.803:=2)(department=IT)(mail=*)(!(description=*Service*)))
```

**What it does:**
- Active users only
- In IT department
- Have email addresses
- Not service accounts

---

## Common Attributes

| Attribute | Description | Example Value |
|-----------|-------------|---------------|
| `cn` | Common Name | "John Doe" |
| `sAMAccountName` | Username | "jdoe" |
| `mail` | Email address | "jdoe@corp.com" |
| `displayName` | Display name | "Doe, John" |
| `department` | Department | "IT" |
| `title` | Job title | "System Administrator" |
| `memberOf` | Group membership | "CN=IT-Staff,OU=Groups,DC=corp,DC=example,DC=com" |
| `description` | Description | "Service Account for monitoring" |
| `userAccountControl` | Account flags | See below |
| `whenCreated` | Creation date | "20240101000000.0Z" |

## UserAccountControl Flags

Common bit flags (use bitwise matching):

| Flag | Decimal | Hex | Description |
|------|---------|-----|-------------|
| DISABLED | 2 | 0x2 | Account is disabled |
| NORMAL_ACCOUNT | 512 | 0x200 | Normal user account |
| DONT_EXPIRE_PASSWORD | 65536 | 0x10000 | Password never expires |

**Bitwise match example:**
```ldap
(userAccountControl:1.2.840.113556.1.4.803:=2)
```
This matches if bit 2 (DISABLED) is set.

To exclude disabled accounts:
```ldap
(!userAccountControl:1.2.840.113556.1.4.803:=2)
```

## Testing Your Filter

### Method 1: Using ldapsearch (Linux/Mac)
```bash
ldapsearch -x -H ldap://dc.corp.example.com \
  -D "CN=LDAP Reader,OU=Service Accounts,DC=corp,DC=example,DC=com" \
  -w "password" \
  -b "DC=corp,DC=example,DC=com" \
  "(&(objectClass=user)(objectCategory=person))" \
  dn sAMAccountName mail displayName
```

### Method 2: Using the UI
1. Go to Settings → LDAP
2. Configure your LDAP settings
3. Click "Test Connection" to verify settings work
4. Enter your filter in the import dialog
5. Click "Import Users"
6. Check the response message for errors

### Method 3: Check Server Logs
The enhanced import function now logs to PHP error log:
```bash
# On the server
tail -f /var/log/apache2/error.log  # or /var/log/nginx/error.log
```

Look for lines starting with `LDAP Import:`

## Troubleshooting

### "LDAP search failed: Operations error"
- Your filter syntax is invalid
- Try a simpler filter first
- Verify parentheses are balanced

### "LDAP search failed: No such object"
- Your Base DN is incorrect
- Verify the OU exists: `OU=Users,DC=corp,DC=example,DC=com`

### "LDAP bind failed: Invalid credentials"
- Bind DN or password is wrong
- Verify: `CN=LDAP Reader,OU=Service Accounts,DC=corp,DC=example,DC=com`

### "Imported 0 users"
- Filter matched no users
- Try the default filter first
- Check logs for "Found X entries"

### "LDAP extension not installed"
- Install PHP LDAP extension:
  ```bash
  sudo apt-get install php-ldap
  sudo systemctl restart apache2
  ```

## Recommended Filters by Scenario

### Small Organization (< 100 users)
Use default - imports all active users:
```ldap
(&(objectClass=user)(objectCategory=person)(!userAccountControl:1.2.840.113556.1.4.803:=2))
```

### Large Organization - IT Department Only
Set Base DN to IT OU:
```
OU=IT,OU=Departments,DC=corp,DC=example,DC=com
```
Use default filter.

### Large Organization - Specific Group
Use group membership filter:
```ldap
(&(objectClass=user)(objectCategory=person)(!userAccountControl:1.2.840.113556.1.4.803:=2)(memberOf=CN=Asset-Managers,OU=Groups,DC=corp,DC=example,DC=com))
```

### Mixed Environment - Exclude Service Accounts
```ldap
(&(objectClass=user)(objectCategory=person)(!userAccountControl:1.2.840.113556.1.4.803:=2)(!(description=*service*)))
```

## Example API Call

```javascript
// Import with custom filter
fetch('/api.php?action=ldap_import', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    filter: "(&(objectClass=user)(objectCategory=person)(!userAccountControl:1.2.840.113556.1.4.803:=2)(department=IT))"
  })
})
.then(r => r.json())
.then(data => console.log(data));
```

Response:
```json
{
  "success": true,
  "message": "Imported 15 users, skipped 3 (duplicates/errors)",
  "imported": 15,
  "skipped": 3
}
```
