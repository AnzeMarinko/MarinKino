(() => {
    const dialog = document.getElementById("mailConfirmDialog");
    if (!dialog) return;
    let target = "false";
    let sending = false;
    const buttons = [...document.querySelectorAll("[data-send-mail]")];
    buttons.forEach(button => button.addEventListener("click", () => {
        if (sending) return;
        target = button.dataset.sendMail;
        document.getElementById("mailConfirmText").textContent = target === "true"
            ? "Filmski izbor bo poslan vsem uporabnikom s shranjenim e-naslovom. Si preveril predogled, seznam prejemnikov in testno sporočilo?"
            : "Testno sporočilo bo poslano na tvoje shranjene e-naslove. Nadaljuješ?";
        dialog.showModal();
    }));
    document.getElementById("cancelMail").addEventListener("click", () => dialog.close());
    document.getElementById("confirmMail").addEventListener("click", async () => {
        if (sending) return;
        dialog.close(); sending = true; buttons.forEach(button => { button.disabled = true; });
        const status = document.getElementById("results"); status.hidden = false; status.dataset.kind = "success"; status.textContent = "Pošiljam e-pošto. Počakaj na rezultat; strani ne osvežuj.";
        document.getElementById("mailRecipientsResult").hidden = true;
        try {
            const response = await fetch("/admin/send_emails", { method: "POST", headers: { "Content-Type": "application/json", "X-CSRFToken": document.querySelector('meta[name="csrf-token"]').content }, body: JSON.stringify({ whole_list: target }) });
            const data = await response.json();
            if (!response.ok || data.error || !Array.isArray(data.emails) || !Number.isFinite(Number(data.sent))) throw new Error(data.error || "unavailable");
            status.textContent = `Pošiljanje zaključeno. Sporočilo poslano ${data.sent} uporabnikom.`;
            document.getElementById("emails").textContent = data.emails.join("\n");
            document.getElementById("mailRecipientsResult").hidden = false;
        } catch (_error) {
            status.dataset.kind = "error";
            status.textContent = "Pošiljanja ni bilo mogoče potrditi. Pred ponovitvijo preveri poštni predal ali sistemski dnevnik, da ne pošlješ podvojenih sporočil.";
        } finally { sending = false; buttons.forEach(button => { button.disabled = false; }); }
    });
})();
