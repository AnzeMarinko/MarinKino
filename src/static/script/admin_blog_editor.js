function freshCsrfToken() {
    const meta = document.querySelector('meta[name="csrf-token"]');
    return fetch('/csrf-token', {credentials: 'same-origin', cache: 'no-store'})
        .then(r => r.json())
        .then(d => { meta.content = d.csrf_token; return d.csrf_token; })
        .catch(() => meta.content);
}

document.addEventListener('DOMContentLoaded', function() {
    const contentEditor = document.getElementById('content-editor');
    const form = document.getElementById('blogEditorForm');
    let dirty = false;
    let saving = false;
    let revision = 0;
    const markDirty = () => {
        revision++;
        dirty = true;
        document.getElementById('saveStatus').textContent = 'Neshranjene spremembe · shrani z gumbom ali Ctrl / ⌘ + S.';
    };
    form.addEventListener('input', markDirty);
    window.addEventListener('beforeunload', event => {
        if (dirty) { event.preventDefault(); event.returnValue = ''; }
    });
    var simplemde = window.EasyMDE ? new EasyMDE({
        element: document.getElementById("content-editor"),
        spellChecker: false,
        autoDownloadFontAwesome: false,
        nativeSpellcheck: true,
        status: ["lines", "words"],
        toolbar: [
            "bold", "italic", "strikethrough", "|",
            "heading-1", "heading-2", "heading-3", "|",
            "code", "quote", "unordered-list", "ordered-list", "|",
            "link", "image", "table", "horizontal-rule", "|",
            "guide"
        ],
        previewRender: markdown => window.marked && window.DOMPurify ? DOMPurify.sanitize(marked.parse(markdown)) : ""
    }) : {
        value: () => contentEditor.value,
        codemirror: { on: (_event, handler) => contentEditor.addEventListener('input', handler), save: () => {}, focus: () => contentEditor.focus() }
    };
    if (!window.EasyMDE) showAlert('Naprednega editorja ni mogoče naložiti. Vsebino lahko normalno napišeš in shraniš v spodnjem polju.', 'info');

    function updatePreview() {
        const markdown = simplemde.value();
        if (markdown) {
            if (window.marked && window.DOMPurify) document.getElementById('content-preview').innerHTML = DOMPurify.sanitize(marked.parse(markdown));
            else document.getElementById('content-preview').textContent = markdown;
        } else {
            document.getElementById('content-preview').innerHTML = '<p class="text-muted">Predogled se bo prikazal tukaj</p>';
        }
    }

    simplemde.codemirror.on('change', updatePreview);
    simplemde.codemirror.on('change', markDirty);

    document.getElementById('preview-tab').addEventListener('shown.bs.tab', function (e) {
        updatePreview();
    });

    updatePreview();

    // Character counter za SEO opis
    const seoDescriptionTextarea = document.getElementById('seo_description');
    const seoDescriptionCount = document.getElementById('seo-description-count');

    function updateSeoDescriptionCount() {
        const count = seoDescriptionTextarea.value.length;
        seoDescriptionCount.textContent = count;
        seoDescriptionCount.style.color = count > 155 ? '#dc3545' : count > 140 ? '#ffc107' : '#6c757d';
    }

    seoDescriptionTextarea.addEventListener('input', updateSeoDescriptionCount);
    updateSeoDescriptionCount(); // Initial count

    const imageFileInput = document.getElementById('image_file');
    const imageCropContainer = document.getElementById('image-crop-container');
    const imagePreview = document.getElementById('image-preview');
    const imagePreviewWrapper = document.getElementById('image-preview-wrapper');
    const cropBox = document.getElementById('crop-box');
    const cropX = document.getElementById('crop_x');
    const cropY = document.getElementById('crop_y');
    const cropW = document.getElementById('crop_w');
    const cropH = document.getElementById('crop_h');
    const cropSizeRange = document.getElementById('crop-size-range');
    const cropSizeLabel = document.getElementById('crop-size-label');
    const cropXRange = document.getElementById('crop-x-range');
    const cropYRange = document.getElementById('crop-y-range');
    const imageUploadStatus = document.getElementById('imageUploadStatus');
    const retryImagePreview = document.getElementById('retryImagePreview');
    const galleryEditor = window.createBlogGalleryEditor({
        input: imageFileInput,
        list: document.getElementById('blogGalleryEditor'),
        empty: document.getElementById('galleryEmpty'),
        retry: retryImagePreview,
        coverDescription: document.getElementById('image_desc'),
        onStatus: (message, error = false) => {
            imageUploadStatus.textContent = message;
            imageUploadStatus.hidden = !message;
            imageUploadStatus.dataset.kind = error ? 'error' : 'success';
        },
        onChange: markDirty,
        onSelect: entry => {
            hideCropContainer();
            if (entry?.file && entry.isCover && entry.status === 'ready') {
                imagePreview.dataset.galleryKey = entry.key;
                showCropContainer(); imagePreview.src = entry.url;
            }
        }
    });

    let cropState = {
        dragging: false,
        offsetX: 0,
        offsetY: 0,
    };

    function showCropContainer() {
        imageCropContainer.classList.remove('d-none');
    }

    function hideCropContainer() {
        imageCropContainer.classList.add('d-none');
        cropX.value = cropY.value = cropW.value = cropH.value = '';
    }

    function setCropBox(left, top, width, height) {
        const imgWidth = imagePreview.clientWidth;
        const imgHeight = imagePreview.clientHeight;
        height = width * 5 / 6;
        if (height > imgHeight) { height = imgHeight; width = height * 6 / 5; }

        const maxLeft = Math.max(0, imgWidth - width);
        const maxTop = Math.max(0, imgHeight - height);
        left = Math.min(Math.max(0, left), maxLeft);
        top = Math.min(Math.max(0, top), maxTop);

        cropBox.style.left = left + 'px';
        cropBox.style.top = top + 'px';
        cropBox.style.width = width + 'px';
        cropBox.style.height = height + 'px';

        updateCropInputs();
    }

    function updateCropInputs() {
        const imgWidth = imagePreview.clientWidth;
        const imgHeight = imagePreview.clientHeight;
        const left = parseFloat(cropBox.style.left || 0);
        const top = parseFloat(cropBox.style.top || 0);
        const width = parseFloat(cropBox.style.width || 0);
        const height = parseFloat(cropBox.style.height || 0);

        if (!imgWidth || !imgHeight || !width || !height) {
            cropX.value = cropY.value = cropW.value = cropH.value = '';
            return;
        }

        cropX.value = (left / imgWidth).toFixed(6);
        cropY.value = (top / imgHeight).toFixed(6);
        cropW.value = (width / imgWidth).toFixed(6);
        cropH.value = (height / imgHeight).toFixed(6);
        galleryEditor.setCrop({ x: Number(cropX.value), y: Number(cropY.value), w: Number(cropW.value), h: Number(cropH.value) });
        cropSizeLabel.textContent = `${Math.round((width / imgWidth) * 100)}%`;
        cropSizeRange.value = Math.round((width / imgWidth) * 100);
        cropXRange.value = imgWidth > width ? Math.round(left / (imgWidth - width) * 100) : 0;
        cropYRange.value = imgHeight > height ? Math.round(top / (imgHeight - height) * 100) : 0;
    }

    function initCropBox() {
        const imgWidth = imagePreview.clientWidth;
        const imgHeight = imagePreview.clientHeight;
        if (!imgWidth || !imgHeight) {
            return;
        }

        let width = Math.min(imgWidth * 0.8, imgHeight * 6 / 5);
        let height = width * 5 / 6;
        if (height > imgHeight) {
            height = imgHeight * 0.8;
            width = height * 6 / 5;
        }

        const left = (imgWidth - width) / 2;
        const top = (imgHeight - height) / 2;
        setCropBox(left, top, width, height);
        cropSizeRange.value = Math.round((width / imgWidth) * 100);

        const maxLeft = Math.max(0, imgWidth - width);
        const maxTop = Math.max(0, imgHeight - height);
        cropXRange.value = maxLeft > 0 ? Math.round((left / maxLeft) * 100) : 10;
        cropYRange.value = maxTop > 0 ? Math.round((top / maxTop) * 100) : 10;
    }

    function validateCropSelection() {
        const error = galleryEditor.validate();
        if (error) { showAlert(error, 'danger'); return false; }
        return true;
    }

    imagePreview.addEventListener('load', () => {
        const entry = galleryEditor.active();
        if (!entry?.file || entry.key !== imagePreview.dataset.galleryKey || !imagePreview.naturalWidth) return;
        const crop = entry.crop;
        if (crop) setCropBox(crop.x * imagePreview.clientWidth, crop.y * imagePreview.clientHeight, crop.w * imagePreview.clientWidth, crop.h * imagePreview.clientHeight);
        else initCropBox();
    });
    imagePreview.addEventListener('error', () => {
        if (galleryEditor.active()?.file) { hideCropContainer(); showAlert('Predogleda ni mogoče prikazati. Ponovno izberi sliko.', 'error'); }
    });

    window.addEventListener('resize', function() {
        if (!imageCropContainer.classList.contains('d-none')) {
            const values = [cropX, cropY, cropW, cropH].map(input => Number(input.value));
            if (values[2] && values[3]) setCropBox(values[0] * imagePreview.clientWidth, values[1] * imagePreview.clientHeight, values[2] * imagePreview.clientWidth, values[3] * imagePreview.clientHeight);
            else initCropBox();
        }
    });

    cropBox.addEventListener('pointerdown', function(e) {
        e.preventDefault();
        cropState.dragging = true;
        cropState.offsetX = e.clientX - parseFloat(cropBox.style.left || 0);
        cropState.offsetY = e.clientY - parseFloat(cropBox.style.top || 0);
        cropBox.setPointerCapture(e.pointerId);
    });
    cropBox.addEventListener('pointermove', function(e) {
        if (!cropState.dragging) return;
        setCropBox(e.clientX - cropState.offsetX, e.clientY - cropState.offsetY, parseFloat(cropBox.style.width), parseFloat(cropBox.style.height));
        markDirty();
    });
    cropBox.addEventListener('pointercancel', () => { cropState.dragging = false; });

    cropXRange.addEventListener('input', function() {
        const imgWidth = imagePreview.clientWidth;
        const imgHeight = imagePreview.clientHeight;
        if (!imgWidth || !imgHeight) {
            return;
        }

        const cropBoxWidth = parseFloat(cropBox.style.width || 0);
        const maxLeft = Math.max(0, imgWidth - cropBoxWidth);
        const left = (parseInt(this.value) / 100) * maxLeft;
        const top = parseFloat(cropBox.style.top || 0);
        const width = parseFloat(cropBox.style.width || 0);
        const height = parseFloat(cropBox.style.height || 0);

        setCropBox(left, top, width, height);
    });

    cropYRange.addEventListener('input', function() {
        const imgWidth = imagePreview.clientWidth;
        const imgHeight = imagePreview.clientHeight;
        if (!imgWidth || !imgHeight) {
            return;
        }

        const cropBoxHeight = parseFloat(cropBox.style.height || 0);
        const maxTop = Math.max(0, imgHeight - cropBoxHeight);
        const left = parseFloat(cropBox.style.left || 0);
        const top = (parseInt(this.value) / 100) * maxTop;
        const width = parseFloat(cropBox.style.width || 0);
        const height = parseFloat(cropBox.style.height || 0);

        setCropBox(left, top, width, height);
    });

    document.addEventListener('pointerup', function() {
        cropState.dragging = false;
    });

    imagePreviewWrapper.addEventListener('scroll', function() {
        if (cropState.dragging) {
            cropState.dragging = false;
        }
    });

    cropSizeRange.addEventListener('input', function() {
        const imgWidth = imagePreview.clientWidth;
        const imgHeight = imagePreview.clientHeight;
        if (!imgWidth || !imgHeight) {
            return;
        }
        let width = Math.min(imgWidth * (Number(this.value) / 100), imgHeight * 6 / 5);
        let height = width * 5 / 6;
        if (height > imgHeight) {
            height = imgHeight * 0.9;
            width = height * 6 / 5;
        }
        const left = (imgWidth - width) / 2;
        const top = (imgHeight - height) / 2;
        setCropBox(left, top, width, height);
    });

    form.addEventListener('submit', function(e) {
        e.preventDefault();
        saveBlogPost();
    });

    // Ctrl+S za shranjevanje (AJAX, ne redirect)
    document.addEventListener('keydown', function(e) {
        if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 's') {
            e.preventDefault();
            if (validateCropSelection()) {
                saveBlogPost();
            }
        }
    });

    function saveBlogPost() {
        if (saving || !form.reportValidity() || !validateCropSelection()) return;
        if (!simplemde.value().trim()) {
            showAlert('Vnesi vsebino objave, preden jo shraniš.', 'danger');
            simplemde.codemirror.focus();
            return;
        }
        simplemde.codemirror.save();
        const submitBtn = form.querySelector('button[type="submit"]');
        const savedRevision = revision;
        const originalText = submitBtn.textContent;
        saving = true;
        let savedOnServer = false;
        submitBtn.disabled = true;
        submitBtn.textContent = "Shranjujem...";

        const formData = new FormData(form);
        galleryEditor.serialize(formData);
        const requestId = `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;
        const targetUrl = form.action || window.location.href;
        let phase = 'request-setup';
        console.info('[blog-save] started', {
            requestId,
            method: 'POST',
            targetUrl,
            pageUrl: window.location.href,
            formFields: [...formData.keys()].sort(),
            uploadCount: [...formData.keys()].filter(key => key.startsWith('gallery_file_')).length,
            byteCount: [...formData.values()].reduce((total, value) => total + (value instanceof File ? value.size : String(value).length), 0)
        });

        const requestBytes = [...formData.values()].reduce(
            (total, value) => total + (
                value instanceof File
                    ? value.size
                    : new Blob([String(value)]).size
            ),
            0
        );
        if (requestBytes > 39 * 1024 * 1024) {
            showAlert(
                'Zahteva je prevelika. Skupna velikost objave ne sme presegati 40 MB.',
                'error'
            );
            submitBtn.disabled = false;
            submitBtn.textContent = originalText;
            saving = false;
            return;
        }

        phase = 'fetch';
        freshCsrfToken().then(token => fetch(targetUrl, {
            method: 'POST',
            body: formData,
            headers: {
                'X-Requested-With': 'XMLHttpRequest',
                "X-CSRFToken": token,
                "X-Request-ID": requestId
            }
        }))
        .then(async response => {
            phase = 'response-body';
            console.info('[blog-save] response', {
                requestId,
                status: response.status,
                contentType: response.headers.get('Content-Type'),
                redirected: response.redirected,
                responseUrl: response.url
            });
            const contentType = response.headers.get('Content-Type') || '';
            let data = {};
            if (contentType.includes('application/json')) {
                data = await response.json();
            } else {
                console.error('[blog-save] invalid JSON response', {
                    requestId,
                    status: response.status,
                    contentType,
                    responseUrl: response.url
                });
                if (response.status === 413) {
                    throw new Error(
                        'Zahteva je prevelika (HTTP 413). Zmanjšaj velikost ali število slik.'
                    );
                }
                throw new Error(
                    `Strežnik je vrnil neveljaven odgovor (HTTP ${response.status}).`
                );
            }
            if (!response.ok) throw new Error(data.message || 'Shranjevanje ni uspelo.');
            savedOnServer = data.success === true;
            return data;
        })
        .then(data => {
            if (data.success) {
                phase = 'apply-response';
                console.info('[blog-save] server accepted save', {
                    requestId,
                    postId: data.post_id,
                    imageCount: data.images?.length,
                    uploadCount: Object.keys(data.image_uploads || {}).length
                });
                // Prikaži sporočilo o uspehu
                showAlert('Blog objava shranjena.', 'success');
                dirty = revision !== savedRevision;
                document.getElementById('saveStatus').textContent = dirty ? 'Nove spremembe še niso shranjene.' : 'Vse spremembe shranjene.';
                galleryEditor.acceptSaved(data, dirty);
                if (!dirty) { imageFileInput.value = ''; hideCropContainer(); }
                if (data.post_id) {
                    const editUrl = data.edit_url || `/admin/blog/edit/${encodeURIComponent(data.post_id)}`;
                    form.action = editUrl;
                    window.history.replaceState(null, '', editUrl);
                    const editLink = document.getElementById('editSavedLink');
                    editLink.href = editUrl;
                    editLink.hidden = false;
                }
            } else {
                console.error('[blog-save] server rejected save', {
                    requestId,
                    message: data.message
                });
                showAlert(data.message || 'Napaka pri shranjevanju.', 'error');
            }
            submitBtn.disabled = false;
            submitBtn.textContent = data.success ? 'Shrani spremembe' : originalText;
            saving = false;
        })
        .catch(error => {
            console.error('[blog-save] failed', {
                requestId,
                phase,
                targetUrl,
                pageUrl: window.location.href,
                savedOnServer,
                error,
                stack: error.stack
            });
            const message = savedOnServer
                ? 'Objava je shranjena, vendar urejevalnika ni bilo mogoče posodobiti. Ponovno naloži stran.'
                : 'Napaka pri shranjevanju: ' + error.message;
            showAlert(message, 'error');
            submitBtn.disabled = false;
            submitBtn.textContent = savedOnServer ? 'Shrani spremembe' : originalText;
            saving = false;
        });
    }

    function showAlert(message, type) {
        const notice = document.getElementById('editorMessage');
        notice.textContent = message;
        notice.dataset.kind = type === 'danger' || type === 'error' ? 'error' : 'success';
        notice.hidden = false;
    }
    // Send mail to subscribers
    const sendMailBtn = document.getElementById('send-mail-btn');
    if (sendMailBtn) {
        sendMailBtn.addEventListener('click', function() {
            if (dirty || saving) { showAlert('Najprej shrani spremembe objave. Nato jo lahko pošlješ naročnikom.', 'danger'); return; }
            if (!confirm('Ali res želite poslati e-pošto vsem naročnikom?')) return;
            sendMailBtn.disabled = true;
            sendMailBtn.textContent = 'Pošiljam...';
            freshCsrfToken().then(token => fetch(window.location.pathname.replace('/edit/', '/send_mail/'), {
                method: 'POST',
                headers: {
                    'X-Requested-With': 'XMLHttpRequest',
                    'X-CSRFToken': token,
                },
            }))
            .then(r => r.json())
            .then(data => {
                if (data.success) {
                    showAlert(data.message || 'E-pošta poslana.', 'success');
                    sendMailBtn.textContent = 'Pošlji naročnikom (poslano)';
                    sendMailBtn.classList.remove('btn-warning');
                    sendMailBtn.classList.add('btn-success');
                    sendMailBtn.disabled = true;
                } else {
                    showAlert(data.message || 'Napaka pri pošiljanju.', 'danger');
                    sendMailBtn.disabled = false;
                    sendMailBtn.textContent = 'Pošlji naročnikom';
                }
            })
            .catch(err => {
                showAlert('Napaka pri pošiljanju: ' + err.message, 'danger');
                sendMailBtn.disabled = false;
                sendMailBtn.textContent = 'Pošlji naročnikom';
            });
        });
    }
});
