(() => {
  const form = document.querySelector('.auth-form');
  if (!form) return;
  const syncToggle = (button) => {
    const input = document.getElementById(button.dataset.passwordToggle);
    const visible = input.type === 'text';
    button.textContent = visible ? 'Skrij' : 'Pokaži';
    button.setAttribute('aria-pressed', String(visible));
    button.setAttribute('aria-label', `${visible ? 'Skrij' : 'Pokaži'}: ${document.querySelector(`label[for="${input.id}"]`).textContent}`);
  };
  form.querySelectorAll('[data-password-toggle]').forEach((button) => {
    button.hidden = false;
    button.addEventListener('click', () => {
      const input = document.getElementById(button.dataset.passwordToggle);
      input.type = input.type === 'password' ? 'text' : 'password';
      syncToggle(button);
    });
  });
  const password = form.querySelector('#password');
  const confirm = form.querySelector('#password_confirm');
  if (!password || !confirm) return;
  const validateMatch = () => {
    confirm.setCustomValidity(confirm.value && confirm.value !== password.value ? 'Gesli se ne ujemata. Ponovi novo geslo.' : '');
  };
  [password, confirm].forEach((input) => input.addEventListener('input', validateMatch));
  form.addEventListener('submit', (event) => {
    validateMatch();
    if (!form.reportValidity()) event.preventDefault();
  });
  const generate = document.getElementById('generate-password');
  if (!generate || !window.crypto?.getRandomValues) return;
  generate.hidden = false;
  const randomIndex = (length) => {
    const value = new Uint32Array(1);
    const limit = 0x100000000 - (0x100000000 % length);
    do { crypto.getRandomValues(value); } while (value[0] >= limit);
    return value[0] % length;
  };
  generate.addEventListener('click', () => {
    const groups = ['abcdefghijklmnopqrstuvwxyz', 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', '0123456789', '!@#$%^&*_-='];
    const alphabet = groups.join('');
    const chars = groups.map((group) => group[randomIndex(group.length)]);
    while (chars.length < 20) chars.push(alphabet[randomIndex(alphabet.length)]);
    for (let index = chars.length - 1; index > 0; index -= 1) {
      const other = randomIndex(index + 1);
      [chars[index], chars[other]] = [chars[other], chars[index]];
    }
    password.value = confirm.value = chars.join('');
    password.type = confirm.type = 'text';
    form.querySelectorAll('[data-password-toggle]').forEach(syncToggle);
    validateMatch();
    document.getElementById('password-feedback').textContent = 'Močno geslo je ustvarjeno in prikazano. Pred shranjevanjem ga shrani v upravljalnik gesel.';
  });
})();
