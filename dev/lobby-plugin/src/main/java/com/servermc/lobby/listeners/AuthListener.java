package com.servermc.lobby.listeners;

import com.servermc.lobby.LobbyCore;
import com.servermc.lobby.managers.AuthManager;
import com.servermc.lobby.managers.PremiumManager;
import net.kyori.adventure.text.Component;
import net.kyori.adventure.text.format.TextColor;
import net.kyori.adventure.text.format.TextDecoration;
import org.bukkit.Location;
import org.bukkit.entity.Player;
import org.bukkit.event.Cancellable;
import org.bukkit.event.EventHandler;
import org.bukkit.event.EventPriority;
import org.bukkit.event.Listener;
import org.bukkit.event.block.BlockBreakEvent;
import org.bukkit.event.block.BlockPlaceEvent;
import org.bukkit.event.entity.EntityDamageByEntityEvent;
import org.bukkit.event.entity.EntityDamageEvent;
import org.bukkit.event.inventory.InventoryClickEvent;
import org.bukkit.event.player.*;

/**
 * Auth Listener - Blocks all player actions until they are authenticated.
 * Also handles the premium question click commands (/premium_yes, /premium_no).
 */
public class AuthListener implements Listener {

    private final LobbyCore plugin;

    private static final TextColor RED = TextColor.color(255, 85, 85);
    private static final TextColor GRAY = TextColor.color(170, 170, 170);
    private static final TextColor WHITE = TextColor.color(255, 255, 255);
    private static final TextColor GOLD = TextColor.color(255, 170, 0);

    public AuthListener(LobbyCore plugin) {
        this.plugin = plugin;
    }

    // ═══ Block movement until authenticated ═══

    @EventHandler(priority = EventPriority.LOWEST)
    public void onMove(PlayerMoveEvent event) {
        if (shouldBlock(event.getPlayer())) {
            Location from = event.getFrom();
            Location to = event.getTo();
            if (to != null && (from.getX() != to.getX() || from.getZ() != to.getZ())) {
                Location newTo = from.clone();
                newTo.setPitch(to.getPitch());
                newTo.setYaw(to.getYaw());
                event.setTo(newTo);
            }
        }
    }

    // ═══ Block chat (except auth commands) ═══

    @EventHandler(priority = EventPriority.LOWEST)
    public void onChat(AsyncPlayerChatEvent event) {
        if (shouldBlock(event.getPlayer())) {
            event.setCancelled(true);
            event.getPlayer().sendMessage(Component.empty()
                    .append(Component.text(" ❌ ", RED))
                    .append(Component.text("Debes autenticarte primero.", GRAY)));
        }
    }

    // ═══ Block commands (except /login, /register, /premium_*) ═══

    @EventHandler(priority = EventPriority.LOWEST)
    public void onCommand(PlayerCommandPreprocessEvent event) {
        Player player = event.getPlayer();
        String msg = event.getMessage().toLowerCase();
        String cmd = msg.split(" ")[0];

        // ═══ Handle premium response FIRST (before any blocking) ═══
        PremiumManager pm = plugin.getPremiumManager();
        if (cmd.equals("/premium_yes") && pm.isPendingQuestion(player.getUniqueId())) {
            event.setCancelled(true);
            pm.setPremium(player, true);
            return;
        }
        if (cmd.equals("/premium_no") && pm.isPendingQuestion(player.getUniqueId())) {
            event.setCancelled(true);
            pm.setPremium(player, false);
            return;
        }

        // ═══ Block commands if not authenticated ═══
        if (shouldBlock(player)) {
            if (cmd.equals("/login") || cmd.equals("/register")) {
                return; // Allow auth commands
            }
            event.setCancelled(true);
            player.sendMessage(Component.empty()
                    .append(Component.text(" ❌ ", RED))
                    .append(Component.text("Debes autenticarte primero.", GRAY)));
        }
    }

    // ═══ Block interactions ═══

    @EventHandler(priority = EventPriority.LOWEST)
    public void onInteract(PlayerInteractEvent event) {
        if (shouldBlock(event.getPlayer())) {
            event.setCancelled(true);
        }
    }

    @EventHandler(priority = EventPriority.LOWEST)
    public void onInteractEntity(PlayerInteractEntityEvent event) {
        if (shouldBlock(event.getPlayer())) {
            event.setCancelled(true);
        }
    }

    @EventHandler(priority = EventPriority.LOWEST)
    public void onInventoryClick(InventoryClickEvent event) {
        if (event.getWhoClicked() instanceof Player player && shouldBlock(player)) {
            event.setCancelled(true);
        }
    }

    @EventHandler(priority = EventPriority.LOWEST)
    public void onBlockBreak(BlockBreakEvent event) {
        if (shouldBlock(event.getPlayer())) {
            event.setCancelled(true);
        }
    }

    @EventHandler(priority = EventPriority.LOWEST)
    public void onBlockPlace(BlockPlaceEvent event) {
        if (shouldBlock(event.getPlayer())) {
            event.setCancelled(true);
        }
    }

    @EventHandler(priority = EventPriority.LOWEST)
    public void onDropItem(PlayerDropItemEvent event) {
        if (shouldBlock(event.getPlayer())) {
            event.setCancelled(true);
        }
    }

    @EventHandler(priority = EventPriority.LOWEST)
    public void onDamage(EntityDamageEvent event) {
        if (event.getEntity() instanceof Player player && shouldBlock(player)) {
            event.setCancelled(true);
        }
    }

    @EventHandler(priority = EventPriority.LOWEST)
    public void onDamageByEntity(EntityDamageByEntityEvent event) {
        if (event.getDamager() instanceof Player player && shouldBlock(player)) {
            event.setCancelled(true);
        }
    }

    // ═══ Lobby protections (always active) ═══

    @EventHandler
    public void onHunger(org.bukkit.event.entity.FoodLevelChangeEvent event) {
        // No hunger in lobby
        if (event.getEntity() instanceof Player) {
            event.setCancelled(true);
        }
    }

    /**
     * Check if a player's actions should be blocked.
     */
    private boolean shouldBlock(Player player) {
        AuthManager auth = plugin.getAuthManager();
        return auth.needsAuth(player.getUniqueId()) && !auth.isAuthenticated(player.getUniqueId());
    }
}
