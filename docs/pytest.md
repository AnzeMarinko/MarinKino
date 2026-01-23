# MarinKino API testiranje

Navodila za testiranje ključnih delov API-ja.

## Nastavitev pytest

```bash
pip install pytest pytest-cov pytest-mock python-dotenv
```

## Testiranje

### Zaženi vse teste
```bash
./scripts/run_tests.sh all
```

### Zaženi z merjenjem pokritosti
```bash
./scripts/run_tests.sh coverage
```

### Zaženi za specifičen del testov
```bash
./scripts/run_tests.sh auth
```
