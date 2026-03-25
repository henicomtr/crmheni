function loadMessages() {
    fetch("/api/messages/latest")
        .then(res => res.json())
        .then(data => {
            const container = document.getElementById("messages");
            container.innerHTML = "";

            data.forEach(msg => {
                const div = document.createElement("div");
                div.style.padding = "8px";
                div.style.borderBottom = "1px solid #ddd";
                div.innerHTML = "<strong>" + msg.sender + "</strong>: " + msg.content;
                container.appendChild(div);
            });
        });
}

setInterval(loadMessages, 4000);
loadMessages();
