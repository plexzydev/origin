package com.servermc.prisongens.listeners;

import com.servermc.prisongens.PrisonGens;
import com.servermc.prisongens.gui.ItemStatsMenu;
import org.bukkit.entity.Player;
import org.bukkit.event.EventHandler;
import org.bukkit.event.Listener;
import org.bukkit.event.block.Action;
import org.bukkit.event.player.PlayerInteractEvent;
import org.bukkit.inventory.ItemStack;

/**
 * Shift + Click derecho con un GEN o Robot en la mano abre su
 * menú de estadísticas. Click derecho con el pico abre las mejoras.
 */
public class ItemInteractListener implements Listener {

    private final PrisonGens plugin;

    public ItemInteractListener(PrisonGens plugin) {
        this.plugin = plugin;
    }

    @EventHandler
    public void onInteract(PlayerInteractEvent event) {
        if (event.getAction() != Action.RIGHT_CLICK_AIR && event.getAction() != Action.RIGHT_CLICK_BLOCK) return;
        ItemStack item = event.getItem();
        if (item == null) return;
        Player player = event.getPlayer();

        boolean isGen = plugin.getGenItemFactory().isGen(item);
        boolean isRobot = plugin.getRobotItemFactory().isRobot(item);

        if ((isGen || isRobot) && player.isSneaking()) {
            event.setCancelled(true);
            new ItemStatsMenu(plugin, player, item).open();
            return;
        }

        if (isGen || isRobot) {
            // Evitar colocar el ítem como bloque
            event.setCancelled(true);
            player.sendMessage("§e§lℹ §7Usa §fShift+Click derecho §7para ver sus estadísticas,");
            player.sendMessage("§7o insértalo mediante el NPC correspondiente de tu isla.");
            return;
        }

        if (plugin.getEnchantManager().isPickaxe(item)) {
            event.setCancelled(true);
            new com.servermc.prisongens.gui.PickaxeMenu(plugin, player).open();
        }
    }
}
