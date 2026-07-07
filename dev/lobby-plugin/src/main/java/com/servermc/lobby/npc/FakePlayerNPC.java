package com.servermc.lobby.npc;

import com.mojang.authlib.GameProfile;
import com.mojang.authlib.properties.Property;
import net.minecraft.network.protocol.game.*;
import net.minecraft.server.MinecraftServer;
import net.minecraft.server.level.ClientInformation;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.server.level.ServerPlayer;
import net.minecraft.server.network.ServerGamePacketListenerImpl;
import net.minecraft.world.entity.player.Player.BedSleepingProblem;
import org.bukkit.Bukkit;
import org.bukkit.Location;
import org.bukkit.craftbukkit.CraftServer;
import org.bukkit.craftbukkit.CraftWorld;
import org.bukkit.craftbukkit.entity.CraftPlayer;
import org.bukkit.entity.Player;
import org.bukkit.profile.PlayerProfile;
import org.bukkit.profile.PlayerTextures;

import java.util.EnumSet;
import java.util.UUID;

/**
 * Fake Player NPC - Creates a real player-looking entity using NMS.
 * Shows the full body with the specified player's skin.
 */
public class FakePlayerNPC {

    private final ServerPlayer nmsPlayer;
    private final int entityId;

    public FakePlayerNPC(Location location, String skinOwnerName) {
        MinecraftServer server = ((CraftServer) Bukkit.getServer()).getServer();
        ServerLevel level = ((CraftWorld) location.getWorld()).getHandle();

        // Create GameProfile with random UUID and string name (empty names can break client rendering)
        GameProfile profile = new GameProfile(UUID.randomUUID(), UUID.randomUUID().toString().substring(0, 8));

        // Fetch skin from a real player profile
        try {
            com.destroystokyo.paper.profile.PlayerProfile bukkitProfile = Bukkit.createProfile(skinOwnerName);
            if (bukkitProfile.complete(true)) {
                for (com.destroystokyo.paper.profile.ProfileProperty prop : bukkitProfile.getProperties()) {
                    profile.getProperties().put(prop.getName(), new Property(prop.getName(), prop.getValue(), prop.getSignature()));
                }
            }
        } catch (Exception e) {
            Bukkit.getLogger().warning("[LobbyCore] Error obteniendo skin de " + skinOwnerName + ": " + e.getMessage());
        }

        // Create the NMS ServerPlayer
        this.nmsPlayer = new ServerPlayer(server, level, profile, ClientInformation.createDefault());
        this.entityId = nmsPlayer.getId();

        // Fix for NullPointerException when generating PlayerInfo update packets (player.connection.latency() causes crash)
        try {
            java.lang.reflect.Field f = sun.misc.Unsafe.class.getDeclaredField("theUnsafe");
            f.setAccessible(true);
            sun.misc.Unsafe unsafe = (sun.misc.Unsafe) f.get(null);
            this.nmsPlayer.connection = (ServerGamePacketListenerImpl) unsafe.allocateInstance(ServerGamePacketListenerImpl.class);
        } catch (Exception e) {
            Bukkit.getLogger().warning("[LobbyCore] Error creando conexion falsa: " + e.getMessage());
        }

        // Set position and rotation
        nmsPlayer.setPos(location.getX(), location.getY(), location.getZ());
        nmsPlayer.setRot(location.getYaw(), location.getPitch());
        nmsPlayer.setYHeadRot(location.getYaw());
    }

    public int getEntityId() {
        return entityId;
    }

    /**
     * Show this NPC to a specific player by sending packets.
     */
    public void showTo(Player viewer) {
        ServerGamePacketListenerImpl conn = ((CraftPlayer) viewer).getHandle().connection;

        // 1. Add to player info (needed before spawning)
        conn.send(new ClientboundPlayerInfoUpdatePacket(
                ClientboundPlayerInfoUpdatePacket.Action.ADD_PLAYER,
                nmsPlayer));

        // 2. Spawn the entity
        conn.send(new ClientboundAddEntityPacket(
                nmsPlayer.getId(),
                nmsPlayer.getUUID(),
                nmsPlayer.getX(),
                nmsPlayer.getY(),
                nmsPlayer.getZ(),
                nmsPlayer.getXRot(),
                nmsPlayer.getYRot(),
                nmsPlayer.getType(),
                0,
                nmsPlayer.getDeltaMovement(),
                nmsPlayer.getYHeadRot()
        ));

        // 3. Set head rotation
        conn.send(new ClientboundRotateHeadPacket(nmsPlayer, 
                (byte) ((nmsPlayer.getYHeadRot() * 256.0F) / 360.0F)));

        // 4. Set skin layers visible (all parts: hat, jacket, sleeves, pants)
        nmsPlayer.getEntityData().set(
                net.minecraft.world.entity.player.Player.DATA_PLAYER_MODE_CUSTOMISATION,
                (byte) 0x7F // All skin parts visible
        );
        conn.send(new ClientboundSetEntityDataPacket(
                nmsPlayer.getId(),
                nmsPlayer.getEntityData().getNonDefaultValues()
        ));

        // Hide nametag using Bukkit Scoreboard Team
        Bukkit.getScheduler().runTask(com.servermc.lobby.LobbyCore.getInstance(), () -> {
            org.bukkit.scoreboard.Scoreboard board = Bukkit.getScoreboardManager().getMainScoreboard();
            org.bukkit.scoreboard.Team npcTeam = board.getTeam("npc_hidden");
            if (npcTeam == null) {
                npcTeam = board.registerNewTeam("npc_hidden");
                npcTeam.setOption(org.bukkit.scoreboard.Team.Option.NAME_TAG_VISIBILITY, org.bukkit.scoreboard.Team.OptionStatus.NEVER);
            }
            npcTeam.addEntry(nmsPlayer.getGameProfile().getName());
        });

        // 5. Remove from tab list after a slight delay
        // Removing from tablist might despawn in modern MC unless handled by client correctly. 
        // We will try sending the remove packet after 20 ticks (1 second) so the skin loads.
        Bukkit.getScheduler().runTaskLater(
            com.servermc.lobby.LobbyCore.getInstance(), () -> {
                if (viewer.isOnline()) {
                    conn.send(new ClientboundPlayerInfoRemovePacket(
                            java.util.List.of(nmsPlayer.getUUID())));
                }
            }, 20L);
    }

    /**
     * Hide this NPC from a specific player.
     */
    public void hideFrom(Player viewer) {
        ServerGamePacketListenerImpl conn = ((CraftPlayer) viewer).getHandle().connection;
        conn.send(new ClientboundRemoveEntitiesPacket(nmsPlayer.getId()));
        conn.send(new ClientboundPlayerInfoRemovePacket(
                java.util.List.of(nmsPlayer.getUUID())));
    }

    /**
     * Destroy this NPC completely.
     */
    public void destroy() {
        for (Player p : Bukkit.getOnlinePlayers()) {
            hideFrom(p);
        }
    }

    public UUID getUUID() {
        return nmsPlayer.getUUID();
    }
}
