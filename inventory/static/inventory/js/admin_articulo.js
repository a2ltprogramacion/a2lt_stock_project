document.addEventListener('DOMContentLoaded', function() {
    function toggleCombos() {
        var tipoField = document.getElementById('id_tipo');
        var recetaInline = document.getElementById('receta_combo-group');
        if (tipoField && recetaInline) {
            recetaInline.style.display = tipoField.value === 'COMBO' ? 'block' : 'none';
        }
    }

    function toggleSeriales() {
        var serialCheckbox = document.getElementById('id_usa_serial');
        var serialInline = document.getElementById('seriales-group');
        if (serialCheckbox && serialInline) {
            serialInline.style.display = serialCheckbox.checked ? 'block' : 'none';
        }
    }

    var tipoField = document.getElementById('id_tipo');
    if (tipoField) {
        tipoField.addEventListener('change', toggleCombos);
        toggleCombos();
    }

    var serialCheckbox = document.getElementById('id_usa_serial');
    if (serialCheckbox) {
        serialCheckbox.addEventListener('change', toggleSeriales);
        toggleSeriales();
    }
});
