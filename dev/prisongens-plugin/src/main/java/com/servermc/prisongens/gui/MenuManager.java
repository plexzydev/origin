package com.servermc.prisongens.gui;

import com.servermc.prisongens.PrisonGens;
import org.bukkit.entity.Player;
import org.bukkit.event.EventHandler;
import org.bukkit.event.Listener;
import org.bukkit.event.inventory.InventoryClickEvent;
import org.bukkit.event.inventory.InventoryCloseEvent;
import org.bukkit.event.inventory.InventoryDragEvent;
import org.bukkit.event.player.AsyncPlayerChatEvent;

import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import java.util.function.Consumer;

/**
 * Router central de menús + entrada por chat (para renombrar GENS, etc).
 */
public class MenuManager implements Listener {

    private final PrisonGens plugin;
    private final Map<UUID, Consumer<String>> chatInputs = new ConcurrentHashMap<>();

    public MenuManager(PrisonGens plugin) {
        this.plugin = plugin;
    }

    @EventHandler
    public void onClick(InventoryClickEvent event) {
        if (!(event.getInventory().getHolder() instanceof Menu menu)) return;
        if (!(event.getWhoClicked() instanceof Player)) return;

        int raw = event.getRawSlot();
        boolean topClick = raw >= 0 && raw < event.getInventory().getSize();

        if (topClick && menu.allowsInteraction(raw)) {
            // Slot interactivo: dejar que el menú decida
            menu.onClick(event);
            return;
        }

        // Bloquear shift-click desde el inventario del jugador hacia el menú
        if (!topClick && event.isShiftClick()) {
            event.setCancelled(true);
            return;
        }

        if (topClick) {
            event.setCancelled(true);
            menu.onClick(event);
        }
    }

    @EventHandler
    public void onDrag(InventoryDragEvent event) {
        if (!(event.getInventory().getHolder() instanceof Menu menu)) return;
        for (int raw : event.getRawSlots()) {
            if (raw < event.getInventory().getSize() && !menu.allowsInteraction(raw)) {
                event.setCancelled(true);
                return;
            }
        }
    }

    @EventHandler
    public void onClose(InventoryCloseEvent event) {
        if (event.getInventory().getHolder() instanceof Menu menu) {
            menu.onClose(event);
        }
    }

    // ═══ Chat input (renombrar, etc.) ═══

    public void requestChatInput(Player player, String prompt, Consumer<String> callback) {
        player.closeInventory();
        player.sendMessage("§e§l✎ §7" + prompt + " §8(escribe §ccancelar §8para abortar)");
        chatInputs.put(player.getUniqueId(), callback);
    }

    @EventHandler
    public void onChat(AsyncPlayerChatEvent event) {
        Consumer<String> callback = chatInputs.remove(event.getPlayer().getUniqueId());
        if (callback == null) return;
        event.setCancelled(true);
        String msg = event.getMessage().trim();
        org.bukkit.Bukkit.getScheduler().runTask(plugin, () -> {
            if (msg.equalsIgnoreCase("cancelar")) {
                event.getPlayer().sendMessage("§c§l✖ §7Acción cancelada.");
                return;
            }
            callback.accept(msg);
        });
    }
}
