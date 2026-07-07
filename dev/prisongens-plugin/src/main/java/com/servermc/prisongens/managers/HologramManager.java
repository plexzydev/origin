package com.servermc.prisongens.managers;

import com.servermc.prisongens.PrisonGens;
import com.servermc.prisongens.mine.MineManager;
import org.bukkit.Location;
import org.bukkit.World;
import org.bukkit.entity.ArmorStand;
import org.bukkit.entity.Entity;
import org.bukkit.entity.EntityType;

import java.util.*;
import java.util.concurrent.ConcurrentHashMap;

/**
 * HologramManager - Hologramas basados en ArmorStands invisibles.
 * Cada isla tiene un holograma sobre su zona de mina que muestra el estado
 * ("Coloca un GEN" o estadísticas de la mina activa).
 */
public class HologramManager {

    private final PrisonGens plugin;
    /** ArmorStands del holograma de mina por dueño de isla. */
    private final Map<UUID, List<ArmorStand>> mineHolograms = new ConcurrentHashMap<>();

    private static final double LINE_SPACING = 0.28;

    public HologramManager(PrisonGens plugin) {
        this.plugin = plugin;
    }

    /** Reconstruye el holograma de la mina de una isla. */
    public void updateMineHologram(UUID owner) {
        removeMineHologram(owner);

        Location center = plugin.getMineManager().getMineCenter(owner);
        if (center == null) return;
        World world = center.getWorld();
        if (world == null) return;

        MineManager.MineData mine = plugin.getMineManager().getMine(owner);
        List<String> lines = new ArrayList<>();

        if (!mine.hasActiveGen()) {
            lines.add("§6§l⬢ TU MINA §6§l⬢");
            lines.add("§7Coloca un §fGEN §7en el");
            lines.add("§fAdministrador de Minas");
            lines.add("§7para crear tu mina.");
        } else {
            MineManager.Stage stage = plugin.getMineManager().getCurrentStage(owner);
            int depth = plugin.getMineManager().getMineDepth(owner);
            lines.add("§6§l⬢ MINA ACTIVA §6§l⬢");
            lines.add("§7Tamaño: §f" + stage.width() + "x" + stage.width() + "x" + depth);
            lines.add("§7Etapa: §f" + (mine.currentStage + 1) + "§7/§f" + plugin.getMineManager().getStages().size());
            lines.add("§7Puntos: §f" + plugin.getMineManager().computeSizePoints(owner));
            if (plugin.getMineManager().isBlockedByIslandSize(owner)) {
                lines.add("§c⚠ ¡Mejora tu isla para crecer!");
            }
        }

        Location base = center.clone().add(0.5, 3.2 + lines.size() * LINE_SPACING, 0.5);
        List<ArmorStand> stands = new ArrayList<>();
        for (int i = 0; i < lines.size(); i++) {
            Location loc = base.clone().subtract(0, i * LINE_SPACING, 0);
            ArmorStand stand = spawnLine(world, loc, lines.get(i));
            if (stand != null) stands.add(stand);
        }
        mineHolograms.put(owner, stands);
    }

    private ArmorStand spawnLine(World world, Location loc, String text) {
        try {
            ArmorStand stand = (ArmorStand) world.spawnEntity(loc, EntityType.ARMOR_STAND);
            stand.setInvisible(true);
            stand.setMarker(true);
            stand.setGravity(false);
            stand.setSmall(true);
            stand.setBasePlate(false);
            stand.setCustomName(text);
            stand.setCustomNameVisible(true);
            stand.setPersistent(false);
            stand.setInvulnerable(true);
            stand.addScoreboardTag("prisongens_holo");
            return stand;
        } catch (Exception e) {
            plugin.getLogger().warning("[Hologram] Error creando línea: " + e.getMessage());
            return null;
        }
    }

    public void removeMineHologram(UUID owner) {
        List<ArmorStand> stands = mineHolograms.remove(owner);
        if (stands != null) {
            for (ArmorStand s : stands) {
                if (s != null && !s.isDead()) s.remove();
            }
        }
    }

    /** Limpia stands huérfanos de sesiones anteriores y regenera hologramas. */
    public void spawnAll() {
        World world = plugin.getIslandManager().getIslandWorld();
        if (world != null) {
            for (Entity e : world.getEntities()) {
                if (e instanceof ArmorStand && e.getScoreboardTags().contains("prisongens_holo")) {
                    e.remove();
                }
            }
        }
        for (UUID owner : plugin.getIslandManager().getAllIslandOwners()) {
            updateMineHologram(owner);
        }
    }

    public void removeAll() {
        for (UUID owner : new ArrayList<>(mineHolograms.keySet())) {
            removeMineHologram(owner);
        }
    }
}
