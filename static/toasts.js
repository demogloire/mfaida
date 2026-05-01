;(function () {
  const toastOptions = { delay: 4000, autohide: true }

  function escapeHtml(s) {
    const div = document.createElement('div')
    div.textContent = s == null ? '' : String(s)
    return div.innerHTML
  }

  function toastHeadingFromCls(tagCls) {
    const t = (tagCls || '').toLowerCase()
    if (t.includes('danger')) return 'Erreur'
    if (t.includes('success')) return 'Succès'
    if (t.includes('warning')) return 'Attention'
    return 'Information'
  }

  function normalizeBgClass(tags) {
    let c = tags || 'bg-info'
    c = String(c).trim().split(/\s+/)[0]
    if (!c.startsWith('bg-')) c = 'bg-' + c
    return c
  }

  function createToast(message) {
    const template = document.querySelector("[data-toast-template]")
    if (!template) return

    const element = template.cloneNode(true)
    delete element.dataset.toastTemplate
    element.dataset.toastShown = "1"  // empêche showExistingToasts de le reprendre

    const tagCls = normalizeBgClass(message.tags)
    element.classList.add(tagCls)

    const body = element.querySelector("[data-toast-body]")
    if (body) {
      const h = toastHeadingFromCls(tagCls)
      const msg = message.message || ''
      if (tagCls.includes('success')) {
        body.innerHTML =
          '<div class="fw-semibold mb-1">' +
          escapeHtml(h) +
          '</div><div>' +
          escapeHtml(msg) +
          '</div><p class="small mb-0 mt-2 opacity-90">' +
          escapeHtml("L'activité s'est effectuée avec succès.") +
          '</p>'
      } else {
        body.innerHTML =
          '<div class="fw-semibold mb-1">' +
          escapeHtml(h) +
          '</div><div>' +
          escapeHtml(msg) +
          '</div>'
      }
    }

    document.querySelector("[data-toast-container]").appendChild(element)

    const toast = new bootstrap.Toast(element, toastOptions)
    toast.show()

    // Nettoyage du DOM après la fermeture
    element.addEventListener('hidden.bs.toast', () => element.remove())
  }

  // HX-Trigger sur l'élément initiatrice puis bulle avec bubbles:true (htmx ≥1.8).
  // Ecouter document, pas body : hx-target="body" remplace tout le document.body et perd
  // tout listener attaché à l’ancienne instance.
  function consumeMessagesPayload(event) {
    const detail = event.detail
    const list =
      detail && detail.value !== undefined ? detail.value : detail && detail.messages !== undefined ? detail.messages : detail
    if (!Array.isArray(list)) return
    list.forEach(createToast)
  }
  document.addEventListener("messages", consumeMessagesPayload)

  // Affiche les messages déjà présents dans le HTML au chargement (Post-Redirect)
  // Le flag data-toast-shown empêche d'afficher deux fois le même toast (ex: après htmx:afterSwap)
  const showExistingToasts = () => {
    document.querySelectorAll(".toast:not([data-toast-template]):not([data-toast-shown])").forEach((element) => {
      element.dataset.toastShown = "1"
      const toast = new bootstrap.Toast(element, toastOptions)
      toast.show()
      element.addEventListener('hidden.bs.toast', () => element.remove())
    })
  }

  showExistingToasts()
  // Relancer après chaque swap HTMX pour attraper les messages injectés dans la page
  document.addEventListener("htmx:afterSwap", showExistingToasts)
})()
