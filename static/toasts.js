;(function () {
  const toastOptions = { delay: 3000, autohide: true }

  function createToast(message) {
    const template = document.querySelector("[data-toast-template]")
    if (!template) return

    const element = template.cloneNode(true)
    delete element.dataset.toastTemplate
    element.dataset.toastShown = "1"  // empêche showExistingToasts de le reprendre

    // Ajout de la classe (ex: bg-success)
    element.classList.add(message.tags)

    // Injection du texte
    const body = element.querySelector("[data-toast-body]")
    if (body) body.innerText = message.message

    document.querySelector("[data-toast-container]").appendChild(element)

    const toast = new bootstrap.Toast(element, toastOptions)
    toast.show()

    // Nettoyage du DOM après la fermeture
    element.addEventListener('hidden.bs.toast', () => element.remove())
  }

  // Écoute l'événement déclenché par le Middleware (HX-Trigger: "messages")
  document.body.addEventListener("messages", (event) => {
    event.detail.value.forEach(createToast)
  })

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
  document.body.addEventListener("htmx:afterSwap", showExistingToasts)
})()
