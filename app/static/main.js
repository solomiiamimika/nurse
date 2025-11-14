const Header = L.Control.extend({
  onAdd: function() {
    const div = L.DomUtil.create('div', 'map-header');
    div.innerHTML = `
      <div class="brand">Human</div>
      <div class="search-pill">
        <input placeholder="Services search…" />
      </div>
    `;
    L.DomEvent.disableClickPropagation(div);
    return div;
  }
});
map.addControl(new Header({ position: 'topleft' }));
