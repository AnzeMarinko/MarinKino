/* Native forms keep their validation, submitter values and no-JS behaviour. */
(() => {
  const pending = new Map();

  document.addEventListener('submit', (event) => {
    const form = event.target;
    if (!form.matches('form[data-submit-feedback]') || event.defaultPrevented) return;
    if (pending.has(form)) {
      event.preventDefault();
      return;
    }
    const button = event.submitter;
    pending.set(form, {
      busy: form.getAttribute('aria-busy'),
      button,
      disabled: button?.getAttribute('aria-disabled'),
    });
    form.setAttribute('aria-busy', 'true');
    if (button) {
      // The disabled property would remove a named button from submitted data.
      button.setAttribute('aria-disabled', 'true');
      button.classList.add('is-submitting');
    }
  });

  window.addEventListener('pageshow', () => {
    const restore = (element, name, value) => {
      if (value == null) element.removeAttribute(name);
      else element.setAttribute(name, value);
    };
    for (const [form, state] of pending) {
      restore(form, 'aria-busy', state.busy);
      if (state.button) {
        restore(state.button, 'aria-disabled', state.disabled);
        state.button.classList.remove('is-submitting');
      }
    }
    pending.clear();
  });
})();
