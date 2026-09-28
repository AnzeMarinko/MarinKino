"""Static subscription and email copy; public articles use Google Translate."""

BLOG_LANGUAGES = {
    "sl": {
        "name": "Slovenščina",
        "flag": "🇸🇮",
        "direction": "ltr",
        "notice": "Google Translate: avtomatski prevod, možne so napake.",
        "copy_link": "Kopiraj povezavo",
        "link_copied": "Povezava kopirana.",
        "copy_link_prompt": "Kopiraj povezavo:",
    },
    "en": {
        "name": "English",
        "flag": "🇬🇧",
        "direction": "ltr",
        "notice": (
            "Google Translate: automatic translation may contain "
            "errors."
        ),
        "copy_link": "Copy link",
        "link_copied": "Link copied.",
        "copy_link_prompt": "Copy link:",
    },
    "de": {
        "name": "Deutsch",
        "flag": "🇩🇪",
        "direction": "ltr",
        "notice": (
            "Google Translate: Automatische Übersetzungen können "
            "Fehler enthalten."
        ),
        "copy_link": "Link kopieren",
        "link_copied": "Link kopiert.",
        "copy_link_prompt": "Link kopieren:",
    },
    "es": {
        "name": "Español",
        "flag": "🇪🇸",
        "direction": "ltr",
        "notice": (
            "Google Translate: la traducción automática puede contener "
            "errores."
        ),
        "copy_link": "Copiar enlace",
        "link_copied": "Enlace copiado.",
        "copy_link_prompt": "Copiar enlace:",
    },
    "it": {
        "name": "Italiano",
        "flag": "🇮🇹",
        "direction": "ltr",
        "notice": (
            "Google Translate: la traduzione automatica può contenere "
            "errori."
        ),
        "copy_link": "Copia link",
        "link_copied": "Link copiato.",
        "copy_link_prompt": "Copia link:",
    },
    "fr": {
        "name": "Français",
        "flag": "🇫🇷",
        "direction": "ltr",
        "notice": (
            "Google Translate : la traduction automatique peut "
            "contenir des erreurs."
        ),
        "copy_link": "Copier le lien",
        "link_copied": "Lien copié.",
        "copy_link_prompt": "Copier le lien :",
    },
    "pl": {
        "name": "Polski",
        "flag": "🇵🇱",
        "direction": "ltr",
        "notice": (
            "Google Translate: tłumaczenie automatyczne może zawierać "
            "błędy."
        ),
        "copy_link": "Kopiuj link",
        "link_copied": "Link skopiowany.",
        "copy_link_prompt": "Kopiuj link:",
    },
    "uk": {
        "name": "Українська",
        "flag": "🇺🇦",
        "direction": "ltr",
        "notice": (
            "Google Translate: автоматичний переклад може містити "
            "помилки."
        ),
        "copy_link": "Копіювати посилання",
        "link_copied": "Посилання скопійовано.",
        "copy_link_prompt": "Копіювати посилання:",
    },
    "pt": {
        "name": "Português",
        "flag": "🇵🇹",
        "direction": "ltr",
        "notice": "Google Translate: a tradução automática pode conter erros.",
        "copy_link": "Copiar ligação",
        "link_copied": "Ligação copiada.",
        "copy_link_prompt": "Copiar ligação:",
    },
    "ar": {
        "name": "العربية",
        "flag": "🇸🇦",
        "direction": "rtl",
        "notice": "ترجمة Google: قد تحتوي الترجمة الآلية على أخطاء.",
        "copy_link": "نسخ الرابط",
        "link_copied": "تم نسخ الرابط.",
        "copy_link_prompt": "انسخ الرابط:",
    },
    "zh-CN": {
        "name": "简体中文",
        "flag": "🇨🇳",
        "direction": "ltr",
        "notice": "Google 翻译：自动翻译可能包含错误。",
        "copy_link": "复制链接",
        "link_copied": "链接已复制。",
        "copy_link_prompt": "复制链接：",
    },
    "ja": {
        "name": "日本語",
        "flag": "🇯🇵",
        "direction": "ltr",
        "notice": "Google 翻訳：自動翻訳には誤りが含まれる場合があります。",
        "copy_link": "リンクをコピー",
        "link_copied": "リンクをコピーしました。",
        "copy_link_prompt": "リンクをコピー：",
    },
}

_MESSAGES = {
    "sl": {
        "confirmation_subject": "Potrditev naročnine · Rože dobrega",
        "confirmation_intro": "Hvala za zanimanje za blog Rože dobrega.",
        "confirmation_instruction": (
            "Za potrditev naročnine kliknite spodnji gumb."
        ),
        "confirm": "Potrdi naročnino",
        "fallback_link": "Če gumba ne morete klikniti, odprite to povezavo:",
        "expires": "Povezava velja 24 ur.",
        "greeting": "Lep pozdrav,",
        "confirmation_ignore": (
            "To je samodejno sporočilo. Če se niste naročili na obvestila, "
            "lahko to sporočilo prezrete."
        ),
        "new_post_subject": "Nova objava · Rože dobrega",
        "new_post_title": "Nova objava na blogu Rože dobrega",
        "new_post_intro": "Na blogu Rože dobrega vas čaka nova objava.",
        "read_post": "Preberi celotno objavo",
        "unsubscribe": (
            "To je samodejno sporočilo. Če ne želite več prejemati obvestil, "
            "odgovorite na to sporočilo."
        ),
        "subscription_heading": "Naročite se na nove objave",
        "subscription_intro": (
            "Obvestilo o novi objavi vam pošljemo po e-pošti."
        ),
        "email_label": "E-poštni naslov",
        "email_placeholder": "ime@example.com",
        "language_label": "Jezik obvestil",
        "subscribe": "Naroči se",
        "terms_prefix": "Strinjam se s",
        "terms": "pogoji uporabe",
        "terms_join": "in",
        "privacy": "politiko zasebnosti",
        "terms_suffix": ".",
        "terms_required": (
            "Za naročnino sprejmite pogoje uporabe in politiko "
            "zasebnosti."
        ),
        "verify_failed": "Preverjanje ni uspelo. Poskusite znova.",
        "invalid_email": "Vnesite veljaven e-poštni naslov.",
        "retry_later": "Preveč poskusov. Poskusite znova pozneje.",
        "generic_success": (
            "Če je za ta naslov potrebna potrditev, boste prejeli e-pošto. "
            "Preverite tudi mapo z neželeno pošto."
        ),
        "check_email": "Preverite e-pošto in potrdite naročnino.",
        "unavailable": "Naročanje trenutno ni na voljo. Poskusite pozneje.",
        "mail_failed": "Pošiljanje e-pošte ni uspelo. Poskusite pozneje.",
        "invalid_token": "Povezava za potrditev ni veljavna ali je potekla.",
        "confirmed": "Naročnina je potrjena. Hvala za vaše zanimanje!",
        "back_to_blog": "Nazaj na blog",
    },
    "en": {
        "confirmation_subject": "Confirm your subscription · Rože dobrega",
        "confirmation_intro": "Thank you for your interest in Rože dobrega.",
        "confirmation_instruction": (
            "Click the button below to confirm your subscription."
        ),
        "confirm": "Confirm subscription",
        "fallback_link": "If the button does not work, open this link:",
        "expires": "This link expires in 24 hours.",
        "greeting": "Best wishes,",
        "confirmation_ignore": (
            "This is an automated message. If you did not subscribe, "
            "you can ignore this email."
        ),
        "new_post_subject": "New post · Rože dobrega",
        "new_post_title": "A new post on Rože dobrega",
        "new_post_intro": "A new post is waiting for you on Rože dobrega.",
        "read_post": "Read the post in English",
        "unsubscribe": (
            "This is an automated message. To stop receiving notifications, "
            "reply to this email."
        ),
        "subscription_heading": "Subscribe to new posts",
        "subscription_intro": (
            "We will email you when a new post is published."
        ),
        "email_label": "Email address",
        "email_placeholder": "name@example.com",
        "language_label": "Notification language",
        "subscribe": "Subscribe",
        "terms_prefix": "I agree to the",
        "terms": "terms of use",
        "terms_join": "and",
        "privacy": "privacy policy",
        "terms_suffix": ".",
        "terms_required": "Please accept the terms of use and privacy policy.",
        "verify_failed": "Verification failed. Please try again.",
        "invalid_email": "Enter a valid email address.",
        "retry_later": "Too many attempts. Please try again later.",
        "generic_success": (
            "If this address needs confirmation, you will receive an email. "
            "Please also check your spam folder."
        ),
        "check_email": "Check your email and confirm your subscription.",
        "unavailable": (
            "Subscriptions are unavailable. Please try again later."
        ),
        "mail_failed": "We could not send the email. Please try again later.",
        "invalid_token": "This confirmation link is invalid or has expired.",
        "confirmed": "Your subscription is confirmed. Thank you!",
        "back_to_blog": "Back to the blog",
    },
    "de": {
        "confirmation_subject": "Abonnement bestätigen · Rože dobrega",
        "confirmation_intro": "Vielen Dank für Ihr Interesse an Rože dobrega.",
        "confirmation_instruction": (
            "Bestätigen Sie Ihr Abonnement mit der Schaltfläche unten."
        ),
        "confirm": "Abonnement bestätigen",
        "fallback_link": (
            "Falls die Schaltfläche nicht funktioniert, öffnen Sie "
            "diesen Link:"
        ),
        "expires": "Dieser Link ist 24 Stunden gültig.",
        "greeting": "Herzliche Grüße,",
        "confirmation_ignore": (
            "Dies ist eine automatische Nachricht. Wenn Sie sich nicht "
            "angemeldet haben, können Sie diese E-Mail ignorieren."
        ),
        "new_post_subject": "Neuer Beitrag · Rože dobrega",
        "new_post_title": "Ein neuer Beitrag auf Rože dobrega",
        "new_post_intro": "Auf Rože dobrega wartet ein neuer Beitrag auf Sie.",
        "read_post": "Beitrag auf Deutsch lesen",
        "unsubscribe": (
            "Dies ist eine automatische Nachricht. Um keine "
            "Benachrichtigungen "
            "mehr zu erhalten, antworten Sie auf diese E-Mail."
        ),
        "subscription_heading": "Neue Beiträge abonnieren",
        "subscription_intro": (
            "Wir benachrichtigen Sie per E-Mail über neue Beiträge."
        ),
        "email_label": "E-Mail-Adresse",
        "email_placeholder": "name@example.com",
        "language_label": "Sprache der Benachrichtigungen",
        "subscribe": "Abonnieren",
        "terms_prefix": "Ich akzeptiere die",
        "terms": "Nutzungsbedingungen",
        "terms_join": "und die",
        "privacy": "Datenschutzerklärung",
        "terms_suffix": ".",
        "terms_required": (
            "Bitte akzeptieren Sie Nutzungsbedingungen und "
            "Datenschutzerklärung."
        ),
        "verify_failed": (
            "Überprüfung fehlgeschlagen. Bitte versuchen Sie es erneut."
        ),
        "invalid_email": "Geben Sie eine gültige E-Mail-Adresse ein.",
        "retry_later": (
            "Zu viele Versuche. Bitte versuchen Sie es später erneut."
        ),
        "generic_success": (
            "Falls diese Adresse eine Bestätigung benötigt, erhalten Sie "
            "eine E-Mail. Prüfen Sie auch Ihren Spamordner."
        ),
        "check_email": (
            "Prüfen Sie Ihre E-Mails und bestätigen Sie Ihr Abonnement."
        ),
        "unavailable": (
            "Anmeldungen sind derzeit nicht möglich. Bitte versuchen "
            "Sie es später erneut."
        ),
        "mail_failed": (
            "Die E-Mail konnte nicht gesendet werden. Bitte versuchen "
            "Sie es später erneut."
        ),
        "invalid_token": (
            "Dieser Bestätigungslink ist ungültig oder abgelaufen."
        ),
        "confirmed": "Ihr Abonnement ist bestätigt. Vielen Dank!",
        "back_to_blog": "Zurück zum Blog",
    },
    "es": {
        "confirmation_subject": "Confirma tu suscripción · Rože dobrega",
        "confirmation_intro": "Gracias por tu interés en Rože dobrega.",
        "confirmation_instruction": (
            "Pulsa el botón para confirmar tu suscripción."
        ),
        "confirm": "Confirmar suscripción",
        "fallback_link": "Si el botón no funciona, abre este enlace:",
        "expires": "Este enlace caduca en 24 horas.",
        "greeting": "Un cordial saludo,",
        "confirmation_ignore": (
            "Este es un mensaje automático. Si no te has suscrito, "
            "puedes ignorar este correo."
        ),
        "new_post_subject": "Nueva publicación · Rože dobrega",
        "new_post_title": "Una nueva publicación en Rože dobrega",
        "new_post_intro": "Te espera una nueva publicación en Rože dobrega.",
        "read_post": "Leer la publicación en español",
        "unsubscribe": (
            "Este es un mensaje automático. Para dejar de recibir avisos, "
            "responde a este correo."
        ),
        "subscription_heading": "Suscríbete a las nuevas publicaciones",
        "subscription_intro": (
            "Te avisaremos por correo cuando haya una nueva "
            "publicación."
        ),
        "email_label": "Correo electrónico",
        "email_placeholder": "nombre@example.com",
        "language_label": "Idioma de los avisos",
        "subscribe": "Suscribirme",
        "terms_prefix": "Acepto las",
        "terms": "condiciones de uso",
        "terms_join": "y la",
        "privacy": "política de privacidad",
        "terms_suffix": ".",
        "terms_required": (
            "Acepta las condiciones de uso y la política de privacidad."
        ),
        "verify_failed": "La verificación ha fallado. Vuelve a intentarlo.",
        "invalid_email": "Introduce un correo electrónico válido.",
        "retry_later": "Demasiados intentos. Vuelve a intentarlo más tarde.",
        "generic_success": (
            "Si esta dirección necesita confirmación, recibirás un correo. "
            "Revisa también la carpeta de correo no deseado."
        ),
        "check_email": "Revisa tu correo y confirma tu suscripción.",
        "unavailable": "No es posible suscribirse ahora. Inténtalo más tarde.",
        "mail_failed": "No se pudo enviar el correo. Inténtalo más tarde.",
        "invalid_token": (
            "Este enlace de confirmación no es válido o ha caducado."
        ),
        "confirmed": "Tu suscripción está confirmada. ¡Gracias!",
        "back_to_blog": "Volver al blog",
    },
    "it": {
        "confirmation_subject": "Conferma l’iscrizione · Rože dobrega",
        "confirmation_intro": "Grazie per il tuo interesse per Rože dobrega.",
        "confirmation_instruction": (
            "Premi il pulsante qui sotto per confermare l’iscrizione."
        ),
        "confirm": "Conferma iscrizione",
        "fallback_link": (
            "Se il pulsante non funziona, apri questo collegamento:"
        ),
        "expires": "Questo collegamento scade tra 24 ore.",
        "greeting": "Un caro saluto,",
        "confirmation_ignore": (
            "Questo è un messaggio automatico. Se non hai richiesto "
            "l’iscrizione, puoi ignorare questa email."
        ),
        "new_post_subject": "Nuovo articolo · Rože dobrega",
        "new_post_title": "Un nuovo articolo su Rože dobrega",
        "new_post_intro": "Un nuovo articolo ti aspetta su Rože dobrega.",
        "read_post": "Leggi l’articolo in italiano",
        "unsubscribe": (
            "Questo è un messaggio automatico. Per non ricevere più "
            "notifiche, "
            "rispondi a questa email."
        ),
        "subscription_heading": "Iscriviti per ricevere i nuovi articoli",
        "subscription_intro": (
            "Ti avviseremo via email quando uscirà un nuovo articolo."
        ),
        "email_label": "Indirizzo email",
        "email_placeholder": "nome@example.com",
        "language_label": "Lingua delle notifiche",
        "subscribe": "Iscriviti",
        "terms_prefix": "Accetto le",
        "terms": "condizioni d’uso",
        "terms_join": "e",
        "privacy": "l’informativa sulla privacy",
        "terms_suffix": ".",
        "terms_required": (
            "Accetta le condizioni d’uso e l’informativa sulla privacy."
        ),
        "verify_failed": "Verifica non riuscita. Riprova.",
        "invalid_email": "Inserisci un indirizzo email valido.",
        "retry_later": "Troppi tentativi. Riprova più tardi.",
        "generic_success": (
            "Se questo indirizzo richiede conferma, riceverai un’email. "
            "Controlla anche la cartella della posta indesiderata."
        ),
        "check_email": "Controlla l’email e conferma l’iscrizione.",
        "unavailable": (
            "Iscrizioni non disponibili al momento. Riprova più tardi."
        ),
        "mail_failed": "Invio dell’email non riuscito. Riprova più tardi.",
        "invalid_token": (
            "Questo collegamento di conferma non è valido o è scaduto."
        ),
        "confirmed": "La tua iscrizione è confermata. Grazie!",
        "back_to_blog": "Torna al blog",
    },
    "fr": {
        "confirmation_subject": "Confirmez votre abonnement · Rože dobrega",
        "confirmation_intro": "Merci de votre intérêt pour Rože dobrega.",
        "confirmation_instruction": (
            "Cliquez sur le bouton ci-dessous pour confirmer votre "
            "abonnement."
        ),
        "confirm": "Confirmer l’abonnement",
        "fallback_link": "Si le bouton ne fonctionne pas, ouvrez ce lien :",
        "expires": "Ce lien expire dans 24 heures.",
        "greeting": "Bien cordialement,",
        "confirmation_ignore": (
            "Ceci est un message automatique. Si vous n’avez pas demandé "
            "cet abonnement, vous pouvez ignorer cet e-mail."
        ),
        "new_post_subject": "Nouvel article · Rože dobrega",
        "new_post_title": "Un nouvel article sur Rože dobrega",
        "new_post_intro": "Un nouvel article vous attend sur Rože dobrega.",
        "read_post": "Lire l’article en français",
        "unsubscribe": (
            "Ceci est un message automatique. Pour ne plus recevoir "
            "de notifications, répondez à cet e-mail."
        ),
        "subscription_heading": "Abonnez-vous aux nouveaux articles",
        "subscription_intro": (
            "Nous vous avertirons par e-mail à chaque nouvel article."
        ),
        "email_label": "Adresse e-mail",
        "email_placeholder": "nom@example.com",
        "language_label": "Langue des notifications",
        "subscribe": "S’abonner",
        "terms_prefix": "J’accepte les",
        "terms": "conditions d’utilisation",
        "terms_join": "et la",
        "privacy": "politique de confidentialité",
        "terms_suffix": ".",
        "terms_required": (
            "Veuillez accepter les conditions d’utilisation et la "
            "politique de confidentialité."
        ),
        "verify_failed": "La vérification a échoué. Veuillez réessayer.",
        "invalid_email": "Saisissez une adresse e-mail valide.",
        "retry_later": "Trop de tentatives. Veuillez réessayer plus tard.",
        "generic_success": (
            "Si cette adresse doit être confirmée, vous recevrez un e-mail. "
            "Vérifiez également votre dossier de courrier indésirable."
        ),
        "check_email": "Consultez vos e-mails et confirmez votre abonnement.",
        "unavailable": (
            "Les abonnements sont indisponibles. Réessayez plus tard."
        ),
        "mail_failed": "L’envoi de l’e-mail a échoué. Réessayez plus tard.",
        "invalid_token": "Ce lien de confirmation est invalide ou a expiré.",
        "confirmed": "Votre abonnement est confirmé. Merci !",
        "back_to_blog": "Retour au blog",
    },
    "pl": {
        "confirmation_subject": "Potwierdź subskrypcję · Rože dobrega",
        "confirmation_intro": (
            "Dziękujemy za zainteresowanie blogiem Rože dobrega."
        ),
        "confirmation_instruction": (
            "Kliknij przycisk poniżej, aby potwierdzić subskrypcję."
        ),
        "confirm": "Potwierdź subskrypcję",
        "fallback_link": "Jeśli przycisk nie działa, otwórz ten link:",
        "expires": "Ten link wygasa po 24 godzinach.",
        "greeting": "Serdeczne pozdrowienia,",
        "confirmation_ignore": (
            "To jest wiadomość automatyczna. Jeśli nie zamawiasz "
            "subskrypcji, możesz zignorować tę wiadomość."
        ),
        "new_post_subject": "Nowy wpis · Rože dobrega",
        "new_post_title": "Nowy wpis na blogu Rože dobrega",
        "new_post_intro": "Na blogu Rože dobrega czeka na Ciebie nowy wpis.",
        "read_post": "Przeczytaj wpis po polsku",
        "unsubscribe": (
            "To jest wiadomość automatyczna. Aby zrezygnować "
            "z powiadomień, odpowiedz na tę wiadomość."
        ),
        "subscription_heading": "Subskrybuj nowe wpisy",
        "subscription_intro": "Wyślemy Ci e-mail, gdy pojawi się nowy wpis.",
        "email_label": "Adres e-mail",
        "email_placeholder": "imie@example.com",
        "language_label": "Język powiadomień",
        "subscribe": "Subskrybuj",
        "terms_prefix": "Akceptuję",
        "terms": "warunki korzystania",
        "terms_join": "oraz",
        "privacy": "politykę prywatności",
        "terms_suffix": ".",
        "terms_required": (
            "Zaakceptuj warunki korzystania i politykę prywatności."
        ),
        "verify_failed": "Weryfikacja nie powiodła się. Spróbuj ponownie.",
        "invalid_email": "Podaj prawidłowy adres e-mail.",
        "retry_later": "Zbyt wiele prób. Spróbuj ponownie później.",
        "generic_success": (
            "Jeśli ten adres wymaga potwierdzenia, otrzymasz e-mail. "
            "Sprawdź również folder spam."
        ),
        "check_email": "Sprawdź pocztę i potwierdź subskrypcję.",
        "unavailable": "Subskrypcje są chwilowo niedostępne. Spróbuj później.",
        "mail_failed": "Nie udało się wysłać wiadomości. Spróbuj później.",
        "invalid_token": (
            "Ten link potwierdzający jest nieprawidłowy lub wygasł."
        ),
        "confirmed": "Subskrypcja została potwierdzona. Dziękujemy!",
        "back_to_blog": "Wróć do bloga",
    },
    "uk": {
        "confirmation_subject": "Підтвердіть підписку · Rože dobrega",
        "confirmation_intro": "Дякуємо за ваш інтерес до блогу Rože dobrega.",
        "confirmation_instruction": (
            "Натисніть кнопку нижче, щоб підтвердити підписку."
        ),
        "confirm": "Підтвердити підписку",
        "fallback_link": "Якщо кнопка не працює, відкрийте це посилання:",
        "expires": "Посилання дійсне протягом 24 годин.",
        "greeting": "З найкращими побажаннями,",
        "confirmation_ignore": (
            "Це автоматичне повідомлення. Якщо ви не оформлювали "
            "підписку, можете проігнорувати цей лист."
        ),
        "new_post_subject": "Нова публікація · Rože dobrega",
        "new_post_title": "Нова публікація у блозі Rože dobrega",
        "new_post_intro": "У блозі Rože dobrega на вас чекає нова публікація.",
        "read_post": "Читати публікацію українською",
        "unsubscribe": (
            "Це автоматичне повідомлення. Щоб більше не отримувати "
            "сповіщень, надішліть відповідь на цей лист."
        ),
        "subscription_heading": "Підпишіться на нові публікації",
        "subscription_intro": (
            "Ми надішлемо вам лист, коли з’явиться нова публікація."
        ),
        "email_label": "Електронна адреса",
        "email_placeholder": "name@example.com",
        "language_label": "Мова сповіщень",
        "subscribe": "Підписатися",
        "terms_prefix": "Я погоджуюся з",
        "terms": "умовами користування",
        "terms_join": "та",
        "privacy": "політикою конфіденційності",
        "terms_suffix": ".",
        "terms_required": (
            "Погодьтеся з умовами користування та політикою "
            "конфіденційності."
        ),
        "verify_failed": "Перевірка не вдалася. Спробуйте ще раз.",
        "invalid_email": "Введіть дійсну електронну адресу.",
        "retry_later": "Забагато спроб. Спробуйте пізніше.",
        "generic_success": (
            "Якщо ця адреса потребує підтвердження, ви отримаєте лист. "
            "Перевірте також папку зі спамом."
        ),
        "check_email": "Перевірте пошту та підтвердьте підписку.",
        "unavailable": "Підписка наразі недоступна. Спробуйте пізніше.",
        "mail_failed": "Не вдалося надіслати лист. Спробуйте пізніше.",
        "invalid_token": (
            "Посилання для підтвердження недійсне або прострочене."
        ),
        "confirmed": "Вашу підписку підтверджено. Дякуємо!",
        "back_to_blog": "Повернутися до блогу",
    },
    "pt": {
        "confirmation_subject": "Confirme a sua subscrição · Rože dobrega",
        "confirmation_intro": (
            "Agradecemos o seu interesse no blogue Rože dobrega."
        ),
        "confirmation_instruction": (
            "Clique no botão abaixo para confirmar a subscrição."
        ),
        "confirm": "Confirmar subscrição",
        "fallback_link": "Se o botão não funcionar, abra esta ligação:",
        "expires": "Esta ligação expira dentro de 24 horas.",
        "greeting": "Com os melhores cumprimentos,",
        "confirmation_ignore": (
            "Esta é uma mensagem automática. Se não pediu esta "
            "subscrição, pode ignorar este e-mail."
        ),
        "new_post_subject": "Nova publicação · Rože dobrega",
        "new_post_title": "Uma nova publicação no Rože dobrega",
        "new_post_intro": "Uma nova publicação espera por si no Rože dobrega.",
        "read_post": "Ler a publicação em português",
        "unsubscribe": (
            "Esta é uma mensagem automática. Para deixar de receber "
            "notificações, responda a este e-mail."
        ),
        "subscription_heading": "Subscreva as novas publicações",
        "subscription_intro": (
            "Enviaremos um e-mail quando houver uma nova publicação."
        ),
        "email_label": "Endereço de e-mail",
        "email_placeholder": "nome@example.com",
        "language_label": "Idioma das notificações",
        "subscribe": "Subscrever",
        "terms_prefix": "Aceito os",
        "terms": "termos de utilização",
        "terms_join": "e a",
        "privacy": "política de privacidade",
        "terms_suffix": ".",
        "terms_required": (
            "Aceite os termos de utilização e a política de "
            "privacidade."
        ),
        "verify_failed": "A verificação falhou. Tente novamente.",
        "invalid_email": "Introduza um endereço de e-mail válido.",
        "retry_later": "Demasiadas tentativas. Tente novamente mais tarde.",
        "generic_success": (
            "Se este endereço precisar de confirmação, receberá um e-mail. "
            "Verifique também a pasta de spam."
        ),
        "check_email": "Verifique o seu e-mail e confirme a subscrição.",
        "unavailable": "As subscrições estão indisponíveis. Tente mais tarde.",
        "mail_failed": "Não foi possível enviar o e-mail. Tente mais tarde.",
        "invalid_token": "Esta ligação de confirmação é inválida ou expirou.",
        "confirmed": "A sua subscrição foi confirmada. Obrigado!",
        "back_to_blog": "Voltar ao blogue",
    },
    "ar": {
        "confirmation_subject": "تأكيد الاشتراك · Rože dobrega",
        "confirmation_intro": "شكرًا لاهتمامك بمدونة Rože dobrega.",
        "confirmation_instruction": "اضغط على الزر أدناه لتأكيد اشتراكك.",
        "confirm": "تأكيد الاشتراك",
        "fallback_link": "إذا لم يعمل الزر، افتح هذا الرابط:",
        "expires": "تنتهي صلاحية هذا الرابط بعد 24 ساعة.",
        "greeting": "مع أطيب التحيات،",
        "confirmation_ignore": (
            "هذه رسالة تلقائية. إذا لم تطلب الاشتراك، يمكنك تجاهل هذه "
            "الرسالة."
        ),
        "new_post_subject": "تدوينة جديدة · Rože dobrega",
        "new_post_title": "تدوينة جديدة على Rože dobrega",
        "new_post_intro": "تنتظرك تدوينة جديدة على مدونة Rože dobrega.",
        "read_post": "اقرأ التدوينة بالعربية",
        "unsubscribe": (
            "هذه رسالة تلقائية. لإيقاف الإشعارات، يُرجى الرد على هذه "
            "الرسالة."
        ),
        "subscription_heading": "اشترك لتصلك التدوينات الجديدة",
        "subscription_intro": (
            "سنرسل إليك بريدًا إلكترونيًا عند نشر تدوينة جديدة."
        ),
        "email_label": "البريد الإلكتروني",
        "email_placeholder": "name@example.com",
        "language_label": "لغة الإشعارات",
        "subscribe": "اشتراك",
        "terms_prefix": "أوافق على",
        "terms": "شروط الاستخدام",
        "terms_join": "و",
        "privacy": "سياسة الخصوصية",
        "terms_suffix": ".",
        "terms_required": "يُرجى الموافقة على شروط الاستخدام وسياسة الخصوصية.",
        "verify_failed": "فشل التحقق. يُرجى المحاولة مجددًا.",
        "invalid_email": "أدخل عنوان بريد إلكتروني صالحًا.",
        "retry_later": "محاولات كثيرة جدًا. يُرجى المحاولة لاحقًا.",
        "generic_success": (
            "إذا كان هذا العنوان يحتاج إلى تأكيد، فستتلقى رسالة إلكترونية. "
            "تحقق أيضًا من مجلد البريد غير المرغوب فيه."
        ),
        "check_email": "تحقق من بريدك الإلكتروني وأكد اشتراكك.",
        "unavailable": "الاشتراكات غير متاحة حاليًا. يُرجى المحاولة لاحقًا.",
        "mail_failed": "تعذر إرسال الرسالة. يُرجى المحاولة لاحقًا.",
        "invalid_token": "رابط التأكيد غير صالح أو انتهت صلاحيته.",
        "confirmed": "تم تأكيد اشتراكك. شكرًا لك!",
        "back_to_blog": "العودة إلى المدونة",
    },
    "zh-CN": {
        "confirmation_subject": "确认订阅 · Rože dobrega",
        "confirmation_intro": "感谢您关注 Rože dobrega 博客。",
        "confirmation_instruction": "请点击下方按钮确认订阅。",
        "confirm": "确认订阅",
        "fallback_link": "如果按钮无法使用，请打开以下链接：",
        "expires": "此链接将在24小时后失效。",
        "greeting": "祝好！",
        "confirmation_ignore": (
            "这是一封自动发送的邮件。如果您没有申请订阅，请忽略此邮件。"
        ),
        "new_post_subject": "新文章 · Rože dobrega",
        "new_post_title": "Rože dobrega 发布了新文章",
        "new_post_intro": "Rože dobrega 博客上有一篇新文章等您阅读。",
        "read_post": "阅读文章的中文译文",
        "unsubscribe": (
            "这是一封自动发送的邮件。"
            "如果您不想继续接收通知，请回复此邮件。"
        ),
        "subscription_heading": "订阅新文章通知",
        "subscription_intro": "发布新文章时，我们会向您发送电子邮件。",
        "email_label": "电子邮箱",
        "email_placeholder": "name@example.com",
        "language_label": "通知语言",
        "subscribe": "订阅",
        "terms_prefix": "我同意",
        "terms": "使用条款",
        "terms_join": "和",
        "privacy": "隐私政策",
        "terms_suffix": "。",
        "terms_required": "请同意使用条款和隐私政策。",
        "verify_failed": "验证失败，请重试。",
        "invalid_email": "请输入有效的电子邮箱地址。",
        "retry_later": "尝试次数过多，请稍后重试。",
        "generic_success": (
            "如果此邮箱需要确认，您将收到一封邮件。"
            "请同时检查垃圾邮件文件夹。"
        ),
        "check_email": "请检查邮箱并确认订阅。",
        "unavailable": "目前无法订阅，请稍后重试。",
        "mail_failed": "邮件发送失败，请稍后重试。",
        "invalid_token": "此确认链接无效或已过期。",
        "confirmed": "您的订阅已确认，谢谢！",
        "back_to_blog": "返回博客",
    },
    "ja": {
        "confirmation_subject": "購読の確認 · Rože dobrega",
        "confirmation_intro": (
            "Rože dobrega にご関心をお寄せいただき、"
            "ありがとうございます。"
        ),
        "confirmation_instruction": (
            "下のボタンを押して購読を確認してください。"
        ),
        "confirm": "購読を確認する",
        "fallback_link": (
            "ボタンが使えない場合は、こちらのリンクを開いてください："
        ),
        "expires": "このリンクの有効期限は24時間です。",
        "greeting": "どうぞよろしくお願いいたします。",
        "confirmation_ignore": (
            "このメールは自動送信されています。"
            "購読を申し込んでいない場合は、"
            "このメールを無視してください。"
        ),
        "new_post_subject": "新しい記事 · Rože dobrega",
        "new_post_title": "Rože dobrega の新しい記事",
        "new_post_intro": "Rože dobrega に新しい記事が公開されました。",
        "read_post": "記事を日本語で読む",
        "unsubscribe": (
            "このメールは自動送信されています。"
            "通知の配信停止をご希望の場合は、"
            "このメールに返信してください。"
        ),
        "subscription_heading": "新しい記事の通知を受け取る",
        "subscription_intro": (
            "新しい記事が公開されたら、メールでお知らせします。"
        ),
        "email_label": "メールアドレス",
        "email_placeholder": "name@example.com",
        "language_label": "通知の言語",
        "subscribe": "購読する",
        "terms_prefix": "",
        "terms": "利用規約",
        "terms_join": "と",
        "privacy": "プライバシーポリシー",
        "terms_suffix": "に同意します。",
        "terms_required": "利用規約とプライバシーポリシーに同意してください。",
        "verify_failed": "認証に失敗しました。もう一度お試しください。",
        "invalid_email": "有効なメールアドレスを入力してください。",
        "retry_later": (
            "試行回数が多すぎます。しばらくしてからお試しください。"
        ),
        "generic_success": (
            "このアドレスに確認が必要な場合、メールをお送りします。"
            "迷惑メールフォルダーもご確認ください。"
        ),
        "check_email": "メールを確認し、購読を承認してください。",
        "unavailable": (
            "現在、購読を受け付けていません。"
            "後でもう一度お試しください。"
        ),
        "mail_failed": (
            "メールを送信できませんでした。後でもう一度お試しください。"
        ),
        "invalid_token": "この確認リンクは無効か、有効期限が切れています。",
        "confirmed": "購読が確認されました。ありがとうございます！",
        "back_to_blog": "ブログに戻る",
    },
}


def normalize_language(value):
    """Return a supported canonical language code, defaulting to Slovenian."""
    if not isinstance(value, str):
        return "sl"
    code = value.strip().lower().replace("_", "-")
    if code in {"zh", "zh-cn", "zh-hans"}:
        return "zh-CN"
    return code if code in BLOG_LANGUAGES else "sl"


def messages(language):
    """Return independent message dictionaries so callers cannot alter copy."""
    code = normalize_language(language)
    return {
        **_MESSAGES[code],
        "automatic_notice": BLOG_LANGUAGES[code]["notice"],
    }
