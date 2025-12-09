// 1. CARGA INICIAL: Intentamos recuperar el carrito de la memoria
// Si existe 'carrito' en localStorage lo usamos, si no, empezamos con una lista vacía
let carrito = JSON.parse(localStorage.getItem('carrito')) || [];

// Función auxiliar para guardar en memoria cada vez que hacemos un cambio
function guardarEnMemoria() {
    localStorage.setItem('carrito', JSON.stringify(carrito));
}

function agregarAlCarrito(id, nombre, precio, stockMaximo) {
    // Buscar si ya existe en el carrito
    const itemExistente = carrito.find(item => item.id === id);
    
    if (itemExistente) {
        if (itemExistente.cantidad < stockMaximo) {
            itemExistente.cantidad++;
        } else {
            alert("¡No hay más existencia de este producto!");
            return;
        }
    } else {
        carrito.push({ id, nombre, precio, cantidad: 1, max: stockMaximo });
    }
    
    // 2. GUARDAR CAMBIOS y actualizar vista
    guardarEnMemoria();
    actualizarVistaCarrito();
}

function actualizarVistaCarrito() {
    const lista = document.getElementById('lista-carrito');
    const totalSpan = document.getElementById('total-carrito');
    
    lista.innerHTML = '';
    let total = 0;

    carrito.forEach((item, index) => {
        total += item.precio * item.cantidad;
        
        const div = document.createElement('div');
        div.className = 'cart-item';
        div.innerHTML = `
            <span>${item.nombre} (x${item.cantidad})</span>
            <span>$${(item.precio * item.cantidad).toFixed(2)} 
            <button onclick="eliminarDelCarrito(${index})" style="background:none; color:#e74c3c; border:none; width:auto; padding:0 5px; margin-left:10px; cursor:pointer; font-weight:bold;">Eliminar</button>
            </span>
        `;
        lista.appendChild(div);
    });

    if (carrito.length === 0) {
        lista.innerHTML = '<p>Tu carrito está vacío.</p>';
        // Deshabilitar botón si no hay nada
        const btn = document.getElementById('btn-confirmar');
        if(btn) btn.disabled = true;
    } else {
        const btn = document.getElementById('btn-confirmar');
        if(btn) btn.disabled = false;
    }

    totalSpan.innerText = total.toFixed(2);
}

function eliminarDelCarrito(index) {
    carrito.splice(index, 1);
    // Guardar cambios al borrar
    guardarEnMemoria();
    actualizarVistaCarrito();
}

async function enviarPedido(e) {
    e.preventDefault();
    if (carrito.length === 0) return alert("Agrega productos primero.");

    const datos = {
        cliente: {
            nombre: document.getElementById('cliente-nombre').value,
            direccion: document.getElementById('cliente-direccion').value,
            telefono: document.getElementById('cliente-telefono').value,
            correo: document.getElementById('cliente-correo').value
        },
        productos: carrito,
        total: document.getElementById('total-carrito').innerText
    };

    try {
        const response = await fetch('/procesar_pedido', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(datos)
        });

        const result = await response.json();

        if (result.success) {
            alert("✅ ¡Pedido enviado! Gracias por tu compra.");
            
            // 3. LIMPIEZA: Borramos el carrito de la memoria y del código
            localStorage.removeItem('carrito');
            carrito = []; 
            
            document.getElementById('form-pedido').reset();
            actualizarVistaCarrito();
            location.reload(); 
        } else {
            alert("Error: " + result.message);
        }
    } catch (error) {
        console.error(error);
        alert("Hubo un error de conexión.");
    }
}

// 4. INICIALIZAR VISTA: 
// Al cargar la página, dibuja el carrito si había algo guardado en localStorage
document.addEventListener('DOMContentLoaded', () => {
    actualizarVistaCarrito();
});