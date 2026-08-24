// Script para mensajes y confirmaciones
document.addEventListener('DOMContentLoaded', function() {
    // Auto-ocultar mensajes después de 5 segundos
    setTimeout(function() {
        var mensajes = document.getElementsByClassName('alert');
        for(var i = 0; i < mensajes.length; i++) {
            mensajes[i].style.display = 'none';
        }
    }, 5000);

    // Cerrar mensajes al hacer clic en el botón X
    var botonesCerrar = document.getElementsByClassName('close');
    for(var i = 0; i < botonesCerrar.length; i++) {
        botonesCerrar[i].addEventListener('click', function() {
            this.parentElement.style.display = 'none';
        });
    }

    // Confirmación para eliminar
    var botonesEliminar = document.querySelectorAll('.btn-eliminar');
    botonesEliminar.forEach(function(boton) {
        boton.addEventListener('click', function(e) {
            e.preventDefault();
            var nombre = this.getAttribute('data-nombre') || 'este elemento';
            if(confirm('¿Estás seguro de que deseas eliminar ' + nombre + '?')) {
                window.location.href = this.getAttribute('href');
            }
        });
    });
});