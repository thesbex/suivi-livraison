/* Suivi Livraison — interactions légères, sans dépendance. */
(function () {
  "use strict";

  // Lignes de tableau cliquables
  document.querySelectorAll("tr[data-href]").forEach(function (tr) {
    tr.addEventListener("click", function (e) {
      if (e.target.closest("a, button, form, input, select")) return;
      window.location = tr.dataset.href;
    });
  });

  // Confirmation avant action sensible
  document.querySelectorAll("form[data-confirm]").forEach(function (form) {
    form.addEventListener("submit", function (e) {
      if (!window.confirm(form.dataset.confirm)) e.preventDefault();
    });
  });

  // Filtres auto-soumis
  document.querySelectorAll("[data-autosubmit]").forEach(function (el) {
    el.addEventListener("change", function () { el.form.submit(); });
  });

  // Boutons « Copier »
  document.querySelectorAll("[data-copier]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var texte = btn.dataset.copier;
      var fini = function () {
        var initial = btn.textContent;
        btn.textContent = "Copié ✓";
        setTimeout(function () { btn.textContent = initial; }, 1600);
      };
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(texte).then(fini, fini);
      } else {
        var ta = document.createElement("textarea");
        ta.value = texte;
        document.body.appendChild(ta);
        ta.select();
        try { document.execCommand("copy"); } catch (e) {}
        document.body.removeChild(ta);
        fini();
      }
    });
  });

  // Heure réelle pré-remplie à l'heure courante
  document.querySelectorAll("input[data-heure-auto]").forEach(function (input) {
    if (input.value) return;
    var d = new Date();
    input.value =
      String(d.getHours()).padStart(2, "0") + ":" + String(d.getMinutes()).padStart(2, "0");
  });

  // Libellé sous les notations étoilées
  var LIBELLES = { 1: "À améliorer", 2: "Moyen", 3: "Bien", 4: "Très bien", 5: "Excellent" };
  document.querySelectorAll(".etoiles[data-libelle]").forEach(function (bloc) {
    var sortie = document.getElementById(bloc.dataset.libelle);
    if (!sortie) return;
    var maj = function () {
      var coche = bloc.querySelector("input:checked");
      sortie.textContent = coche ? LIBELLES[coche.value] || "" : "";
    };
    bloc.querySelectorAll("input").forEach(function (r) { r.addEventListener("change", maj); });
    maj();
  });

  // Listes de valeurs (lieux, pays) avec option « Autre » ouvrant une saisie libre.
  // Le champ texte porte le nom réel envoyé au serveur ; la liste ne fait que le remplir.
  document.querySelectorAll("[data-liste-select]").forEach(function (select) {
    var bloc = document.querySelector('[data-liste-libre="' + select.dataset.listeSelect + '"]');
    if (!bloc) return;
    var champ = bloc.querySelector("input");

    var synchroniser = function (viderEtFocus) {
      var autre = select.value === "__autre__";
      bloc.hidden = !autre;
      // « required » n'est posé que sur un champ visible : un champ masqué et
      // obligatoire empêcherait la soumission sans message d'erreur affichable.
      champ.required = autre && select.required;
      if (autre) {
        if (viderEtFocus) { champ.value = ""; champ.focus(); }
      } else {
        champ.value = select.value;
      }
    };

    select.addEventListener("change", function () { synchroniser(true); });
    synchroniser(false);
  });

  // Téléphone du convoyeur affiché sous le sélecteur
  var choix = document.getElementById("choix-convoyeur");
  var sortieTel = document.getElementById("tel-convoyeur");
  if (choix && sortieTel) {
    var majTel = function () {
      var opt = choix.options[choix.selectedIndex];
      sortieTel.textContent = (opt && opt.dataset.tel) || "—";
    };
    choix.addEventListener("change", majTel);
    majTel();
  }

  // Disparition des messages flash
  document.querySelectorAll(".flash").forEach(function (f) {
    setTimeout(function () {
      f.style.transition = "opacity .5s, transform .5s";
      f.style.opacity = "0";
      f.style.transform = "translateY(-6px)";
      setTimeout(function () { f.remove(); }, 550);
    }, 5200);
  });
})();
