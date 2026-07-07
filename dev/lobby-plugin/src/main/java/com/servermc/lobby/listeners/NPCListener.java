package com.servermc.lobby.listeners;

import com.servermc.lobby.LobbyCore;
import com.servermc.lobby.managers.NPCManager;
import io.netty.channel.ChannelDuplexHandler;
import io.netty.channel.ChannelHandlerContext;
import net.minecraft.network.protocol.game.ServerboundInteractPacket;
import org.bukkit.Bukkit;
import org.bukkit.craftbukkit.entity.CraftPlayer;
import org.bukkit.entity.Player;
import org.bukkit.event.EventHandler;
import org.bukkit.event.Listener;
import org.bukkit.event.player.PlayerJoinEvent;
import org.bukkit.event.player.PlayerQuitEvent;

import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;

/**
 * NPC Listener - Intercepts packets to detect clicks on fake player NPCs.
 */
public class NPCListener implements Listener {

    private final LobbyCore plugin;
    private final Map<UUID, ChannelDuplexHandler> handlers = new ConcurrentHashMap<>();

    public NPCListener(LobbyCore plugin) {
        this.plugin = plugin;
    }

    @EventHandler
    public void onJoin(PlayerJoinEvent event) {
        // Inject packet listener after a short delay
        Bukkit.getScheduler().runTaskLater(plugin, () -> {
            if (event.getPlayer().isOnline()) {
                injectPacketListener(event.getPlayer());
            }
        }, 5L);
    }

    @EventHandler
    public void onQuit(PlayerQuitEvent event) {
        removePacketListener(event.getPlayer());
    }

    private void injectPacketListener(Player player) {
        ChannelDuplexHandler handler = new ChannelDuplexHandler() {
            @Override
            public void channelRead(ChannelHandlerContext ctx, Object msg) throws Exception {
                if (msg instanceof ServerboundInteractPacket packet) {
                    int entityId = packet.getEntityId();
                    NPCManager npcManager = plugin.getNpcManager();
                    String npcId = npcManager.getNPCIdFromEntityId(entityId);

                    if (npcId != null) {
                        // Handle on main thread
                        Bukkit.getScheduler().runTask(plugin, () -> {
                            if (player.isOnline() && 
                                plugin.getAuthManager().isAuthenticated(player.getUniqueId())) {
                                npcManager.handleNPCClick(player, npcId);
                            }
                        });
                        return; // Don't pass the packet further
                    }
                }
                super.channelRead(ctx, msg);
            }
        };

        handlers.put(player.getUniqueId(), handler);

        var serverPlayer = ((CraftPlayer) player).getHandle();
        var channel = serverPlayer.connection.connection.channel;
        channel.pipeline().addBefore("packet_handler", "lobbycore_npc_" + player.getName(), handler);
    }

    private void removePacketListener(Player player) {
        ChannelDuplexHandler handler = handlers.remove(player.getUniqueId());
        if (handler != null) {
            try {
                var serverPlayer = ((CraftPlayer) player).getHandle();
                var channel = serverPlayer.connection.connection.channel;
                channel.eventLoop().submit(() -> {
                    channel.pipeline().remove(handler);
                });
            } catch (Exception ignored) {}
        }
    }
}
