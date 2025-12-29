document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll(".pokemon-card").forEach(card => {
    const name = card.dataset.pokemon;
    const spriteDiv = card.querySelector(".sprite");
    const typesDiv = card.querySelector(".types");

    fetch(`https://pokeapi.co/api/v2/pokemon/${name}`)
      .then(res => {
        if (!res.ok) throw new Error("Not found");
        return res.json();
      })
      .then(data => {
        // ----- IMAGE -----
        const img = document.createElement("img");
        img.src = data.sprites.front_default;
        img.alt = name;

        spriteDiv.classList.remove("skeleton-image");
        spriteDiv.innerHTML = "";
        spriteDiv.appendChild(img);

        // ----- TYPES -----
        typesDiv.classList.remove("skeleton-types");
        typesDiv.innerHTML = "";

        data.types.forEach(t => {
          const span = document.createElement("span");
          span.textContent = t.type.name;
          typesDiv.appendChild(span);
        });

        // Remove text shimmer
        card.querySelectorAll(".skeleton-text").forEach(el => {
          el.classList.remove("skeleton-text");
        });
      })
      .catch(() => {
        spriteDiv.classList.remove("skeleton-image");
        spriteDiv.textContent = "No image";
      });
  });
});
