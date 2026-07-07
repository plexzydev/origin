package com.servermc.prisongens.listeners;

import com.servermc.prisongens.PrisonGens;
import com.servermc.prisongens.managers.IslandManager;
import com.servermc.prisongens.npc.FakePlayerNPC;
import net.minecraft.server.level.ServerPlayer;
import org.bukkit.Bukkit;
import org.bukkit.Sound;
import org.bukkit.craftbukkit.entity.CraftPlayer;
import org.bukkit.entity.Player;
import org.bukkit.event.EventHandler;
import org.bukkit.event.Listener;
import org.bukkit.event.inventory.InventoryClickEvent;
import org.bukkit.event.player.*;

import java.util.Map;
import java.util.UUID;

public class PlayerListener implements Listener {

    private final PrisonGens plugin;

    public PlayerListener(PrisonGens plugin) {
        this.plugin = plugin;
    }

    @EventHandler
    public void onJoin(PlayerJoinEvent event) {
        event.joinMessage(null);
        Player player = event.getPlayer();
        plugin.getScoreboardManager().createScoreboard(player);

        IslandManager.IslandData island = plugin.getIslandManager().getIsland(player);
        if (island != null) {
            player.teleport(island.getSpawn(plugin.getIslandManager().getIslandWorld()));
            plugin.getIslandManager().applyWorldBorder(player, island);
        }

        // Show all NPCs
        Bukkit.getScheduler().runTaskLater(plugin, () -> {
            plugin.getIslandManager().showNPCsTo(player);
        }, 10L);
    }

    @EventHandler
    public void onQuit(PlayerQuitEvent event) {
        event.quitMessage(null);
        plugin.getScoreboardManager().removeScoreboard(event.getPlayer());
    }

    @EventHandler
    public void onMove(PlayerMoveEvent event) {
        Player player = event.getPlayer();
        if (player.getLocation().getY() < 0) {
            IslandManager.IslandData island = plugin.getIslandManager().getIsland(player);
            if (island != null) {
                player.teleport(island.getSpawn(plugin.getIslandManager().getIslandWorld()));
            } else {
                player.teleport(plugin.getIslandManager().getIslandWorld().getSpawnLocation());
            }
        }
    }

    @EventHandler
    public void onDrop(PlayerDropItemEvent event) {
        if (plugin.getPickaxeManager().isPickaxe(event.getItemDrop().getItemStack())) {
            event.setCancelled(true);
        }
    }

    // Detect NPC click via UseEntity packet - check distance to NPC entities
    @EventHandler
    public void onInteractEntity(PlayerInteractEntityEvent event) {
        Player player = event.getPlayer();
        // Check if clicked entity is near any NPC location
        for (Map.Entry<UUID, FakePlayerNPC> entry : plugin.getIslandManager().getAllNPCs().entrySet()) {
            FakePlayerNPC npc = entry.getValue();
            // NPC entity IDs are server-side only, so we check via packet listener below
        }
    }

    @EventHandler
    public void onInventoryClick(InventoryClickEvent event) {
        if (!(event.getWhoClicked() instanceof Player player)) return;
        String title = event.getView().getTitle();

        if (title.equals("§a§lAjustes de Isla")) {
            event.setCancelled(true);
            int slot = event.getSlot();
            boolean success = false;

            if (slot == 10) success = plugin.getIslandManager().upgradeMemberSlots(player);
            if (slot == 12) success = plugin.getIslandManager().upgradeHopperLimit(player);
            if (slot == 14) success = plugin.getIslandManager().upgradeRegenSpeed(player);
            if (slot == 16) success = plugin.getIslandManager().upgradeGenCapacity(player);

            if (success) {
                player.playSound(player.getLocation(), Sound.ENTITY_PLAYER_LEVELUP, 0.8f, 1.2f);
                player.sendMessage("§a§l✓ §7Mejora comprada.");
                player.closeInventory();
            } else if (slot == 10 || slot == 12 || slot == 14 || slot == 16) {
                player.playSound(player.getLocation(), Sound.ENTITY_VILLAGER_NO, 0.8f, 1.0f);
                player.sendMessage("§c§l✖ §7No tienes suficiente balance.");
            }
        }
    }
}
