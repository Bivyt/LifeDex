document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll(".pokemon-card").forEach(card => {
    const name = card.dataset.pokemon;

    fetch(`https://pokeapi.co/api/v2/pokemon/${name}`)
      .then(res => {
        if (!res.ok) throw new Error("Not found");
        return res.json();
      })
      .then(data => {
        // Sprite
        const img = document.createElement("img");
        img.src = data.sprites.front_default;
        card.querySelector(".sprite").replaceWith(img);

        // Types
        const typesDiv = card.querySelector(".types");
        data.types.forEach(t => {
          const span = document.createElement("span");
          span.textContent = t.type.name;
          typesDiv.appendChild(span);
        });
      })
      .catch(() => {
        card.querySelector(".sprite").textContent = "No image";
      });
  });
});
